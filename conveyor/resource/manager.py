'''
@author: g00357909
'''


import copy
from oslo.config import cfg
import oslo.messaging as messaging

from conveyor.common import plan_status as p_status
from conveyor.common import fileutils
from conveyor.common import jsonutils
from conveyor.common import uuidutils
from conveyor.common import timeutils
from conveyor.common import log as logging
from conveyor.db import api as db_api

from conveyor import exception
from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor import image
from conveyor import heat
from conveyor import manager
from conveyor.resource import resource
from conveyor.resource import rpcapi
from conveyor.resource.driver.instances import InstanceResource
#from conveyor.resource.driver.volumes import VolumeResource
#from conveyor.resource.driver.networks import NetworkResource


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


_plan_opts = [
    cfg.StrOpt('plan_file_path',
                           default='/tmp/',
                           help='The directory to store '
                                'the resources files of plans')
]

cfg.CONF.register_opts(_plan_opts)
plan_file_dir = cfg.CONF.plan_file_path

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
        super(ResourceManager, self).__init__(service_name="conveyor-resource",
                                             *args, **kwargs)

    def get_resource_types(self, context):
        return resource.resource_type
    
    def get_resource_detail(self, context, resource_type, resource_id):
        
        LOG.info("Get %s resource details of <%s>.", resource_type, resource_id)
        
        method_map = {
            "OS::Nova::Server": "self.nova_api.get_server",
            "OS::Nova::KeyPair": "self.nova_api.get_keypair",
            "OS::Nova::Flavor": "self.nova_api.get_flavor",
            "OS::Cinder::Volume": "self.cinder_api.get",
            "OS::Cinder::VolumeType": "self.cinder_api.get_volume_type",
            "OS::Neutron::Net": " self.neutron_api.get_network",
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
            except Exception:
                LOG.error("%s resource <%s> could not be found.", 
                                    resource_type, resource_id)
                raise exception.ResourceNotFound(resource_type=resource_type, 
                                                 resource_id=resource_id)
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
            sort_key = search_opts.pop('sort_key', None)
            sort_dir = search_opts.pop('sort_dir', None)
            res = self.cinder_api.get_all(context, search_opts=search_opts, 
                                                        marker=marker, limit=limit,
                                                        sort_key=sort_key, sort_dir=sort_dir)
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


    def create_plan(self, context, type, resources):
        
        if type not in ["clone", "migrate"]:
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=type)
        
        LOG.info("Begin to create a %s plan by specified resources.", type)
        
        instance_ids = []
        volume_ids = []
        network_ids = []
        router_ids = []
        loadbalancer_ids = []
        stack_ids = []
        
        for res in resources:
            type = res.get('type', '')
            id = res.get('id', '')
            
            if not id or not type:
                LOG.warn("Unresolved id or type, id(%s), type(%s)", id, type)
                continue
            
            if type == 'OS::Nova::Server':
                instance_ids.append(id)
            elif type== 'OS::Cinder::Volume':
                volume_ids.append(id)
            elif type== 'OS::Neutron::Net':
                network_ids.append(id)
            elif type== 'OS::Neutron::Router':
                router_ids.append(id)
            elif type== 'OS::Neutron::LoadBalancer':
                loadbalancer_ids.append(id)
            elif type== 'OS::Heat::Stack':
                stack_ids.append(id)
            else:
                LOG.error("The resource type %s is unsupported.", type)
                raise exception.ResourceTypeNotSupported(resource_type=type)
            
        res_num = len(instance_ids) + len(volume_ids) + len(network_ids) \
                    + len(router_ids) + len(loadbalancer_ids) + len(stack_ids)
        
        if 0 == res_num:
            msg = "No valid resources found, please check the resource id and type."
            LOG.error(msg)
            raise exception.ResourceExtractFailed(reason = msg)
        
        ir = InstanceResource(context)

        if instance_ids:
            ir.extract_instances(instance_ids)
        if volume_ids:
            pass

        new_resources = ir.get_collected_resources()
        new_dependencies = ir.get_collected_dependencies()

        plan_id = uuidutils.generate_uuid()
        new_plan = resource.Plan(plan_id, 'clone', context.project_id, context.user_id, 
                                original_resources=self._replace_res_id(new_resources),
                                original_dependencies=self._replace_res_id(new_dependencies))
        
        _plans[plan_id] = new_plan
        
        dep = {}
        for k,v in new_plan.original_dependencies.items():
            dep[k] = v.to_dict()
        
        LOG.info("Create plan succeed. Plan_id is %s", plan_id)
        
        return plan_id, dep


    def create_plan_by_template(self, context, template):
        
        LOG.debug("Start to create a plan by template.")
        
        expire_time = template.pop('expire_time', '')
        plan_type = template.pop('plan_type', '')
        if plan_type not in ["clone", "migrate"]:
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=type)
        
        template_res = template.get('resources')
        if not template_res or not isinstance(template_res, dict):
            msg = "Template format is not correct. \
                    'resources' field must be a dict and not empty."
            LOG.error(msg)
            raise exception.TemplateValidateFailed(message=msg)
        
        #pop extra properties and verify template
        standard_template = copy.deepcopy(template)
        for key in standard_template['resources'].keys():
            standard_template['resources'][key].pop('extra_properties', None)
        
        stack_kwargs = dict(stack_name='stack_validate',
                            template=standard_template)
        heat_api = heat.API()
        
        try:
            heat_api.preview_stack(context, **stack_kwargs)
        except Exception as e:
            msg = 'Template validate failed. %s' % unicode(e)
            LOG.error(msg)
            raise exception.TemplateValidateFailed(message=unicode(e))

        #generate a new plan
        plan_id = uuidutils.generate_uuid()
        new_plan = resource.Plan(plan_id, plan_type, 
                         context.project_id, context.user_id,
                         expire_at=expire_time,
                         plan_status=p_status.AVAILABLE)

        #extract resources
        resources = {}
        template_res = template.get('resources')
        for key, value in template_res.items():
            res_id = value.get('extra_properties', {}).get('id', '')
            if not res_id:
                msg = 'Template validate failed. No id \
                            found in extra_properties of %s' % key
                LOG.error(msg)
                raise exception.TemplateValidateFailed(message=msg)
            template_res[key].get('extra_properties', {}).pop('id', '')
            resource_obj = resource.Resource(key, 
                                             value.get('type'), 
                                             res_id, 
                                             properties=value.get('properties'),
                                             extra_properties=value.get('extra_properties'))
            resource_obj.rebuild_parameter(template.get('parameters'))
            resources[key] = resource_obj
        
        new_plan.original_resources = resources
        new_plan.rebuild_dependencies(is_original=True)
        
        #save to database and memory
        self._save_plan_to_db(context, new_plan)
        _plans[plan_id] = new_plan
        
        LOG.info("Create plan by template finished. Plan_id is %s", plan_id)
        
        return new_plan.to_dict()
    

    def get_resource_detail_from_plan(self, context, plan_id, resource_id):
        
        LOG.info("Get details of resource %s in plan <%s>", resource_id, plan_id)
        
        #Check whether plan exist. If not found in memory, get plan from db.
        self.get_plan_by_id(context, plan_id)

        plan = _plans.get(plan_id)
        resource = plan.original_resources.get(resource_id)
        if not resource:
            msg = "Resource <%s> not found in plan <%s>" % (resource_id, plan_id)
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        return resource.to_dict()

    def get_plan_by_id(self, context, plan_id):
        
        LOG.info("Get the plan with id of %s", plan_id)
        
        plan = _plans.get(plan_id)
        if plan:
            return plan.to_dict()
        else:
            plan_dict, plan_obj = self._read_plan_from_db(context, plan_id)
            _plans[plan_id] = plan_obj
            return plan_dict
        

    def get_plans(self, context, search_opts=None):
        
        LOG.info("Get all plans.")
        
        plan_list = self.db_api.plan_get_all(context)
        return plan_list


    def delete_plan(self, context, plan_id):
        
        LOG.info("Delete plan with id of %s", plan_id)
        
        #Delete plan in memory if exists
        _plans.pop(plan_id, None)
            
        #Check whether plan exists in database
        try:
            self.db_api.plan_get(context, plan_id)
        except exception:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)

        #Set deleted status in database
        values = {'plan_status': p_status.DELETED, 'deleted': True,
                                     'deleted_at': timeutils.utcnow()}
        self._update_to_db(context, plan_id, values)
    
        #Delete resource files
        field_name = ['original_resources', 'updated_resources']
        for name in field_name:
            full_path = plan_file_dir + plan_id + '.' + name
            fileutils.delete_if_exists(full_path)
            
        #Delete template
        fileutils.delete_if_exists(plan_file_dir + plan_id)
        

    def update_plan(self, context, plan_id, values):
        
        LOG.info("Update plan with id of %s", plan_id)
                
        if not isinstance(values, dict):
            msg = "Update plan failed. 'values' attribute must be a dict."
            LOG.error(msg)
            raise exception.PlanUpdateException(message=msg)
        
        try:
            #Check whether plan exists in database. If exists, put plan into memory.
            self.get_plan_by_id(context, plan_id)
            plan = _plans.get(plan_id)
        except exception:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        
        allowed_properties = ['task_status', 'plan_status', 
                                        'expire_at', 'updated_resources']
        task_status_to_db = resource.TaskStatus.TASKSTATUS
        
        #Verify the keys and values
        for k,v in values.items():
            if k not in allowed_properties:
                msg = "Update plan failed. %s attribute \
                        not found or unsupported to update." % k
                LOG.error(msg)
                raise exception.PlanUpdateException(message=msg)
            elif k == 'plan_status' and v not in p_status.PLAN_STATUS:
                msg = "Update plan failed. '%s' plan_status unsupported." % v
                LOG.error(msg)
                raise exception.PlanUpdateException(message=msg)
            
        #Update to memory
        for k,v in values.items():
            setattr(plan, k, v)
            if k == 'updated_resources':
                plan.rebuild_dependencies()
        
        #special update: activate the plan and save plan to db
        if 'plan_status' in values.keys() \
                            and values['plan_status'] == p_status.AVAILABLE:
            LOG.info('Activate plan <%s> and write it into database.', plan_id)
            self._save_plan_to_db(context, plan)
            return
        
        #Update in database
        if len(values) == 1 and values.keys()[0] == 'task_status' \
                            and values.values()[0] not in task_status_to_db:
            return
        else:
            self._update_to_db(context, plan_id, values)
            

    def _update_to_db(self, context, plan_id, values):
                
        if 'updated_resources' in values.keys():
            full_path = plan_file_dir + plan_id + '.updated_resources'
            self._write_to_file(full_path, values['updated_resources'])
            values['updated_resources'] = full_path
                
        self.db_api.plan_update(context, plan_id, values)

    
    def _save_plan_to_db(self, context, plan):
        if isinstance(plan, resource.Plan):
            plan = plan.to_dict()
        
        plan.pop('original_dependencies', None)
        plan.pop('updated_dependencies', None)
        
        field_name = ['original_resources', 'updated_resources']
        for name in field_name:
            if plan.get(name):
                full_path = plan_file_dir + plan['plan_id'] + '.' + name
                self._write_to_file(full_path, plan[name])
                plan[name] = full_path
            else:
                plan[name] = ''
        
        try:
            self.db_api.plan_create(context, plan)
        except exception as e:
            #Roll back: delete files
            LOG.error(unicode(e))
            for name in field_name:
                full_path = plan_file_dir + plan['plan_id'] + '.' + name
                fileutils.delete_if_exists(full_path)
                
            raise exception.PlanCreateFailed(unicode(e))


    def _read_plan_from_db(self, context, plan_id):
        plan_dict = self.db_api.plan_get(context, plan_id)
        
        field_name = ['original_resources', 'updated_resources']

        for name in field_name:
            if plan_dict.get(name):
                plan_dict[name] = self._read_from_file(plan_dict[name])
                
        plan_obj = resource.Plan.from_dict(plan_dict)
        
        #rebuild dependencies
        plan_obj.rebuild_dependencies(is_original=True)
        plan_obj.rebuild_dependencies()
        
        return plan_obj.to_dict(), plan_obj


    def _write_to_file(self, full_path, data):
        if not data or not full_path:
            return
        with fileutils.file_open(full_path, 'w') as fp:
            jsonutils.dump(data, fp, indent=4)


    def _read_from_file(self, full_path):
        if not full_path:
            return
        with fileutils.file_open(full_path, 'r') as fp:
            return jsonutils.load(fp)


    def _objects_to_dict(self, objs, type):
        
        if not isinstance(objs, list):
            objs = [objs]
        
        res = []
        client_type = type.split('::')[1]
        res_type = type.split('::')[2]
        
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
            LOG.error("The resource type %s is unsupported.", type)
            raise exception.ResourceTypeNotSupported(resource_type=type)
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
    
