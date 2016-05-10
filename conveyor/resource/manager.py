'''
@author: g00357909
'''
import os
import yaml
import copy
from oslo.config import cfg
import oslo.messaging as messaging

from conveyor.common import plan_status as p_status
from conveyor.common import template_format
from conveyor.common import loopingcall
from conveyor.common import fileutils
from conveyor.common import uuidutils
from conveyor.common import timeutils
from conveyor.common import log as logging
from conveyor.db import api as db_api

from conveyor import context as ctxt
from conveyor import exception
from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor import image
from conveyor import heat
from conveyor import manager
from conveyor.resource import resource
from conveyor.resource.driver.instances import InstanceResource
#from conveyor.resource.driver.volumes import VolumeResource
#from conveyor.resource.driver.networks import NetworkResource


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
                        
CONF.import_opt('clear_expired_plan_interval', 'conveyor.common.config')
CONF.import_opt('plan_file_path', 'conveyor.common.config')

plan_file_dir = CONF.plan_file_path

_plans = {}

class ResourceManager(manager.Manager):
    """Get detail resource."""

    target = messaging.Target(version='1.18')

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """  ."""
        self.nova_api = compute.API()
        self.cinder_api = volume.API()
        self.neutron_api = network.API()
        self.glance_api = image.API()
        self.db_api = db_api
        
        #Start periodic task to clear expired plan
        context = ctxt.get_admin_context()
        timer = loopingcall.FixedIntervalLoopingCall(self._clear_expired_plan, context)
        timer.start(interval=CONF.clear_expired_plan_interval)
        
        super(ResourceManager, self).__init__(service_name="conveyor-resource",
                                             *args, **kwargs)

    
    def get_resource_detail(self, context, resource_type, resource_id):
        
        LOG.info("Get %s resource details with id of <%s>.", resource_type, resource_id)
        
        method_map = {
            "OS::Nova::Server": "self.nova_api.get_server",
            "OS::Nova::KeyPair": "self.nova_api.get_keypair",
            "OS::Nova::Flavor": "self.nova_api.get_flavor",
            "OS::Cinder::Volume": "self.cinder_api.get",
            "OS::Cinder::VolumeType": "self.cinder_api.get_volume_type",
            "OS::Neutron::Net": "self.neutron_api.get_network",
            "OS::Neutron::Subnet": "self.neutron_api.get_subnet",
            "OS::Neutron::Router": "self.neutron_api.get_router",
            "OS::Neutron::SecurityGroup": "self.neutron_api.get_security_group",
            "OS::Neutron::FloatingIP": "self.neutron_api.get_floatingip"
        }
        
        if resource_type in method_map.keys():
            try:
                res_obj = eval(method_map[resource_type])(context, resource_id)
                res = self._objects_to_dict(res_obj, resource_type)
                if isinstance(res, list) and len(res) == 1:
                    return res[0]
            except Exception as e:
                msg = "Get %s resource <%s> failed. %s" % \
                            (resource_type, resource_id, unicode(e))
                LOG.error(msg)
                raise exception.ResourceNotFound(message=msg)
        else:
            LOG.error("The resource type %s is unsupported.", resource_type)
            raise exception.ResourceTypeNotSupported(resource_type=resource_type) 
        
    
    def get_resources(self, context, search_opts=None, marker=None, limit=None):
        
        LOG.info("Get resources filtering by: %s", search_opts)
        
        res_type = search_opts.pop("type", "")
        if not res_type:
            LOG.error("The resource type is empty.")
            raise exception.ResourceTypeNotFound()
        
        if res_type == "OS::Nova::Server":
            res = self.nova_api.get_all_servers(context, search_opts=search_opts, 
                                                marker=marker, limit=limit)
        elif res_type == "OS::Nova::KeyPair":
            res = self.nova_api.keypair_list(context)
        elif res_type == "OS::Nova::Flavor":
            res = self.nova_api.flavor_list(context)
        elif res_type == "OS::Nova::AvailabilityZone":
            res = self.nova_api.availability_zone_list(context)
        elif res_type == "OS::Cinder::Volume":
            res = self.cinder_api.get_all(context, search_opts=search_opts)
        elif res_type == "OS::Cinder::VolumeType":
            res = self.cinder_api.volume_type_list(context, search_opts=search_opts)
        elif res_type == "OS::Neutron::Net":
            res = self.neutron_api.network_list(context, **search_opts)
        elif res_type == "OS::Neutron::Subnet":
            res = self.neutron_api.subnet_list(context, **search_opts)
        elif res_type == "OS::Neutron::Router":
            res = self.neutron_api.router_list(context, **search_opts)
        elif res_type == "OS::Neutron::SecurityGroup":
            res = self.neutron_api.secgroup_list(context, **search_opts)
        elif res_type == "OS::Neutron::FloatingIP":
            res = self.neutron_api.floatingip_list(context, **search_opts)
        elif res_type == "OS::Glance::Image":
            opts = {
                    'marker': search_opts.pop('marker', None),
                    'limit': search_opts.pop('limit', None),
                    'page_size': search_opts.pop('page_size', None),
                    'sort_key': search_opts.pop('sort_key', None),
                    'sort_dir': search_opts.pop('sort_dir', None)
                    }
            opts['filters'] = search_opts
            res = self.glance_api.get_all(context, **opts)
        else:
            LOG.error("The resource type %s is unsupported.", res_type)
            raise exception.ResourceTypeNotSupported(resource_type=res_type)
        
        return self._objects_to_dict(res, res_type)


    def create_plan(self, context, plan_type, resources):
        
        if plan_type not in ["clone", "migrate"]:
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=plan_type)
        
        LOG.info("Begin to create a %s plan by resources: %s.", plan_type, resources)
        
        instance_ids = []
        volume_ids = []
        network_ids = []
        router_ids = []
        loadbalancer_ids = []
        stack_ids = []
        
        for res in resources:
            res_type = res.get('type', '')
            res_id = res.get('id', '')
            
            if not res_id or not res_type:
                LOG.warn("Unresolved id or type, id(%s), type(%s)", res_id, res_type)
                continue
            
            if res_type == 'OS::Nova::Server':
                instance_ids.append(res_id)
            elif res_type == 'OS::Cinder::Volume':
                volume_ids.append(res_id)
            elif res_type == 'OS::Neutron::Net':
                network_ids.append(res_id)
            elif res_type == 'OS::Neutron::Router':
                router_ids.append(res_id)
            elif res_type == 'OS::Neutron::LoadBalancer':
                loadbalancer_ids.append(res_id)
            elif res_type == 'OS::Heat::Stack':
                stack_ids.append(res_id)
            else:
                LOG.error("The resource type %s is unsupported.", res_type)
                raise exception.ResourceTypeNotSupported(resource_type=res_type)
            
        res_num = len(instance_ids) + len(volume_ids) + len(network_ids) \
                    + len(router_ids) + len(loadbalancer_ids) + len(stack_ids)
        
        if 0 == res_num:
            msg = "No valid resources found, please check the resource id and type."
            LOG.error(msg)
            raise exception.ResourceExtractFailed(reason=msg)
        
        ir = InstanceResource(context)

        if instance_ids:
            ir.extract_instances(instance_ids)
        if volume_ids:
            pass

        new_resources = ir.get_collected_resources()
        new_dependencies = ir.get_collected_dependencies()

        plan_id = uuidutils.generate_uuid()
        ori_res = self._replace_res_id(new_resources)
        ori_dep = self._replace_res_id(new_dependencies)
        
        new_plan = resource.Plan(plan_id, plan_type, 
                                 context.project_id, 
                                 context.user_id, 
                                 original_resources=ori_res,
                                 original_dependencies=ori_dep)
        
        #Resources of migrate plan are not allowed to be modified, 
        #so 'updated fields' are empty.
        if plan_type == "clone":
            new_plan.updated_resources = copy.deepcopy(ori_res)
            new_plan.updated_dependencies = copy.deepcopy(ori_dep)
        
        #Save to memory.
        _plans[plan_id] = new_plan
        
        #Save to database.
        plan_dict = new_plan.to_dict()
        resource.save_plan_to_db(context, plan_file_dir, plan_dict)
        
        LOG.info("Create plan succeed. Plan_id is %s", plan_id)
        
        return plan_id, plan_dict['original_dependencies']


    def build_plan_by_template(self, context, plan_dict, template):
        LOG.info("Begin to build plan <%s> by template.", plan_dict['plan_id'])
        
        #extract resources
        plan = resource.Plan.from_dict(plan_dict)
        plan_id = plan.plan_id
        resources = {}
        template_res = template.get('resources')
        for key, value in template_res.items():
            res_id = value.get('extra_properties', {}).get('id', '')
            if not res_id:
                msg = 'Template validate failed. No id \
                            found in extra_properties of %s' % key
                LOG.error(msg)
                resource.update_plan_to_db(context, plan_file_dir, plan_id, 
                                           {'plan_status': p_status.ERROR})
                raise exception.TemplateValidateFailed(message=msg)
            template_res[key].get('extra_properties', {}).pop('id', '')
            resource_obj = resource.Resource(key, 
                                             value.get('type'),
                                             res_id, 
                                             properties=value.get('properties'),
                                             extra_properties=value.get('extra_properties'))
            resource_obj.rebuild_parameter(template.get('parameters'))
            resources[key] = resource_obj
        
        plan.original_resources = resources
        plan.rebuild_dependencies(is_original=True)
        plan.plan_status = p_status.AVAILABLE
        
        #Resources of migrate plan are not allowed to be modified, 
        #so 'updated fields' are empty.
        if plan.plan_type == "clone":
            plan.updated_resources = copy.deepcopy(resources)
            plan.updated_dependencies = copy.deepcopy(plan.original_dependencies)
        
        #Save to memory
        _plans[plan_id] = plan
        
        plan_dict = plan.to_dict()
        update_values = {
            'plan_status': p_status.AVAILABLE,
            'original_resources': plan_dict['original_resources'],
            'updated_resources': plan_dict['updated_resources']
        }
        tpl_full_path = plan_file_dir + plan_id + '.template'
        
        try:
            #Update to database
            resource.update_plan_to_db(context, plan_file_dir, plan_id, update_values)
            
            #Save template file
            with fileutils.file_open(tpl_full_path, 'w') as fp:
                yaml.safe_dump(template, fp, default_flow_style=False)
                
            LOG.info("Create plan by template finished. Plan_id is %s, "
                     "and template file has been saved to %s." 
                      % (plan_id, tpl_full_path))
        except Exception as e:
            msg = "Create plan by template failed! %s" % unicode(e)
            LOG.error(msg)
            #Roll back: change plan status to error
            resource.update_plan_to_db(context, plan_file_dir, plan_id, 
                                       {'plan_status': p_status.ERROR})
            raise exception.PlanCreateFailed(message=msg)
        

    def get_resource_detail_from_plan(self, context, plan_id, 
                                      resource_id, is_original=True):
        
        LOG.info("Get details of resource %s in plan <%s>. is_original is %d.", 
                                                resource_id, plan_id, is_original)
        
        #Check whether plan exist. If not found in memory, get plan from db.
        self.get_plan_by_id(context, plan_id)
        plan = _plans.get(plan_id)
        
        if is_original:
            resource = plan.original_resources.get(resource_id)
        else:
            resource = plan.updated_resources.get(resource_id)
            
        if not resource:
            msg = "Resource <%s> not found in plan <%s>" % (resource_id, plan_id)
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        return resource.to_dict()


    def get_plan_by_id(self, context, plan_id, detail=True):
        
        LOG.info("Get plan with id of %s", plan_id)
        
        plan = _plans.get(plan_id)
        if plan:
            return plan.to_dict(detail=detail)
        else:
            LOG.debug("Get plan <%s> from database.", plan_id)
            plan_dict, plan_obj = resource.read_plan_from_db(context, plan_id)
            _plans[plan_id] = plan_obj
            
            if detail:
                return plan_dict
            else:
                fields = ('original_resources', 'updated_resources', 
                          'original_dependencies', 'updated_dependencies')
                for field in fields:
                    plan_dict.pop(field, None)
                return plan_dict
            

    def delete_plan(self, context, plan_id):
        
        LOG.info("Begin to delete plan with id of %s", plan_id)
            
        #Delete plan in memory
        _plans.pop(plan_id, None)
    
        field_name = ['original_resources', 'updated_resources']
        
        try:
            #Detach temporary port of servers.
            self._detach_server_temporary_port(context, plan_id)
            
            #Delete template files
            fileutils.delete_if_exists(plan_file_dir + plan_id + '.template')
            
            #Delete resource files
            for name in field_name:
                full_path = plan_file_dir + plan_id + '.' + name
                fileutils.delete_if_exists(full_path)
                
        except Exception as e:
            msg = "Delete plan <%s> failed. %s" % (plan_id, unicode(e))
            LOG.error(msg)
            resource.update_plan_to_db(context, plan_file_dir, plan_id, 
                                       {'plan_status': p_status.ERROR_DELETING})
            raise exception.PlanDeleteError(message=msg)
        
        #Set deleted status in database
        values = {'plan_status': p_status.DELETED, 'deleted': True,
                                     'deleted_at': timeutils.utcnow()}
        resource.update_plan_to_db(context, plan_file_dir, plan_id, values)
        
        LOG.info("Delete plan with id of %s succeed!", plan_id)


    def update_plan(self, context, plan_id, values):
        LOG.info("Update plan <%s> with values: %s", plan_id, values)
        
        allowed_properties = ['task_status', 'plan_status', 
                              'stack_id', 'expire_at', 'updated_resources']
        
        #Verify the keys and values
        for k,v in values.items():
            if k not in allowed_properties:
                msg = ("Update plan failed. %s field "
                        "not found or unsupported to update." % k)
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
            elif k == 'plan_status' and v not in p_status.PLAN_STATUS:
                msg = "Update plan failed. '%s' plan_status unsupported." % v
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

        #If values contain updated_resources, set update time.
        if 'updated_resources' in values:
            values['updated_at'] = timeutils.utcnow()

        #Update in database
        task_status_to_db = resource.TaskStatus.TASKSTATUS
        values_to_db = copy.deepcopy(values)
        if values_to_db.get('task_status', '') not in task_status_to_db:
            values_to_db.pop('task_status', None)
            
        if values_to_db:
            resource.update_plan_to_db(context, plan_file_dir, plan_id, values_to_db)

        #Update to memory. If exists, update plan, 
        #else extract updated plan into memory.
        if _plans.get(plan_id):
            plan = _plans[plan_id]
        
            for key, value in values.items():
                if key == 'updated_resources':
                    updated_resources = {}
                    for k, v in value.items():
                        updated_resources[k] = resource.Resource.from_dict(v)
                    setattr(plan, key, updated_resources)
                    plan.rebuild_dependencies()
                else:
                    setattr(plan, key, value)
        else:
            plan_dict, plan_obj = resource.read_plan_from_db(context, plan_id)
            _plans[plan_id] = plan_obj
         
        LOG.info("Update plan with id of %s succeed!", plan_id)   


    def _objects_to_dict(self, objs, rtype):
        
        if not isinstance(objs, list):
            objs = [objs]
        
        res = []
        client_type = rtype.split('::')[1]
        res_type = rtype.split('::')[2]
        
        if client_type == "Nova":
            for obj in objs:
                dt = obj.to_dict()
                if len(dt) == 1 and dt.keys()[0].lower() == res_type.lower():
                    res.append(dt.values()[0])
                else:
                    res.append(dt)
        elif client_type in ("Neutron", "Glance", "Cinder") : 
            return objs
        else:
            LOG.error("The resource type %s is unsupported.", rtype)
            raise exception.ResourceTypeNotSupported(resource_type=rtype)
        return res

    
    def _replace_res_id(self, resources):
        new_res = {}
        if isinstance(resources, dict):
            for v in resources.values():
                if isinstance(v, resource.Resource):
                    new_res[v.name] = v
                elif isinstance(v, resource.ResourceDependency):
                    new_res[v.name_in_template] = v
        return new_res
    
    
    def _clear_expired_plan(self, context):
        """
        Search expired plan in database, and detach migrate port
        """
        
        LOG.debug("Searching expired plan.")
        
        #Search expired plan in database.
        exist_expired_plan = False
        plans = self.db_api.plan_get_all(context)
        for plan in plans:
            if self._has_expired(plan):
                exist_expired_plan = True
                plan_id = plan['plan_id']
                LOG.debug('Plan <%s> has expired.', plan_id)
                
                #Detach temporary port
                if plan['plan_status'] not in (p_status.INITIATING):
                    self._detach_server_temporary_port(context, plan_id)
                
                #Change plan status to expired.
                resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                           {'plan_status': p_status.EXPIRED})
        
        if not exist_expired_plan:
            LOG.debug("No expired plan found.")
        else:
            LOG.debug("Complete to clearing expired plan.")


    def _detach_server_temporary_port(self, context, plan_id):
        #Read template file of this plan
        tpl_file_path = plan_file_dir + plan_id + '.template'
        try:
            with fileutils.file_open(tpl_file_path, 'r') as fp:
                template = template_format.parse(fp.read())
        except Exception as e:
            LOG.warn("Plan template not found. %s" % unicode(e))
            return

        resources = template.get('resources', {})
        for res in resources.values():
            if res['type'] == 'OS::Nova::Server':
                server_id = res.get('extra_properties', {}).get('id')
                migrate_port = res.get('extra_properties', {}).get('migrate_port_id')
                
                if not server_id or not migrate_port:
                    continue
                
                try:
                    self.nova_api.migrate_interface_detach(context, 
                                                           server_id, 
                                                           migrate_port)
                    LOG.debug("Detach migrate port of server <%s> succeed.", server_id)
                except Exception as e:
                    LOG.error("Fail to detach migrate port of server <%s>. %s", 
                              server_id, unicode(e))

  
    def _has_expired(self, plan):
        status = (p_status.INITIATING, p_status.CREATING, p_status.AVAILABLE, 
                  p_status.ERROR, p_status.FINISHED)
        
        if isinstance(plan, resource.Plan):
            plan_status = plan.plan_status
            expire_at = plan.expire_at
        else:
            plan_status = plan['plan_status']
            expire_at = plan['expire_at']
        
        if plan_status in status:
            expire_time = timeutils.parse_isotime(str(expire_at))
            if timeutils.is_older_than(expire_time, 0):
                return True

        return False

