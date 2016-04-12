'''
@author: g00357909
'''


import copy
from oslo.config import cfg
import oslo.messaging as messaging

from conveyor.common import uuidutils
from conveyor.common import plan_status
from conveyor.common import log as logging
from conveyor.db import api as db_api

from conveyor import exception
from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor import heat
from conveyor import manager
from conveyor.resource import resource
from conveyor.resource import rpcapi
from conveyor.resource.driver.instances import InstanceResource


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

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
        super(ResourceManager, self).__init__(service_name="conveyor-resource",
                                             *args, **kwargs)

    def get_resource_types(self, context):
        return resource.resource_type
    
    def get_resource_detail(self, context, resource_type, resource_id):
        method_map = {
            "OS::Nova::Server": "self.nova_api.get_server",
            "OS::Nova::KeyPair": "self.nova_api.get_keypair",
            "OS::Nova::Flavor": "self.nova_api.get_flavor",
            "OS::Cinder::Volume": "self.cinder_api.get_volume",
            "OS::Cinder::VolumeType": "self.cinder_api.get_volume_type",
            "OS::Neutron::Net": " self.neutron_api.get_network",
            "OS::Neutron::Subnet": "self.neutron_api.get_subnet",
            "OS::Neutron::Router": "self.neutron_api.get_router",
            "OS::Neutron::SecurityGroup": "self.neutron_api.get_security_group",
            "OS::Neutron::FloatingIP": "self.neutron_api.get_floatingip"
        }
        
        if resource_type in method_map:
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
        res_type = search_opts.pop("type", "")
        if not res_type:
            LOG.error("The resource type is empty.")
            raise exception.ResourceTypeNotFound()
        
        if res_type == "OS::Nova::Server":
            res = self.nova_api.servers_list(context, search_opts=search_opts)
        elif res_type == "OS::Nova::KeyPair":
            res = self.nova_api.keypair_list(context)
        elif res_type == "OS::Nova::Flavor":
            res = self.nova_api.flavor_list(context)
        elif res_type == "OS::Nova::AvailabilityZone":
            res = self.nova_api.availability_zone_list(context)
        elif res_type == "OS::Cinder::Volume":
            res = self.cinder_api.volume_list(context, search_opts=search_opts)
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
        else:
            LOG.error("The resource type %s is unsupported.", res_type)
            raise exception.ResourceTypeNotSupported(resource_type=res_type)
        
        return self._objects_to_dict(res, res_type)


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
        elif client_type == "Neutron": 
            return objs
        elif type == "OS::Cinder::Volume":
            for obj in objs:
                res.append(resource.volume_to_dict(obj))
            return res
        elif type == "OS::Cinder::VolumeType":
            for obj in objs:
                res.append(resource.volume_type_to_dict(obj))
        else:
            LOG.error("The resource type %s is unsupported.", type)
            raise exception.ResourceTypeNotSupported(resource_type=type)
        return res


    def create_plan(self, context, type, resources):
        
        if type not in ["clone", "migrate"]:
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=type)
        
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
        
        new_resources = []
        new_dependencies = []
        
        ir = InstanceResource(context)

        try:
            if instance_ids:
                ir.get_instances_resources(instance_ids)
            if volume_ids:
                pass

            new_resources = ir.get_collected_resources()
            new_dependencies = ir.get_collected_dependencies()
        except Exception as e:
            LOG.error("Resource extract failed! %s", unicode(e))
            raise exception.ResourceExtractFailed(reason=unicode(e))

        plan_id = uuidutils.generate_uuid()
        new_plan = resource.Plan(plan_id, 'clone', context.project_id, context.user_id, 
                                original_resources=self._replace_res_id(new_resources),
                                original_dependencies=self._replace_res_id(new_dependencies))
        
        _plans[plan_id] = new_plan
        #TODO database
        
        dep = {}
        for k,v in new_plan.original_dependencies.items():
            dep[k] = v.to_dict()
        
        return plan_id, dep


    def get_resource_detail_from_plan(self, context, plan_id, resource_id):
        plan = _plans.get(plan_id)
        if not plan:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        resource = plan.original_resources.get(resource_id)
        if not resource:
            msg = "Plan %s hasn't resource %s" % (plan_id, resource_id)
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        return resource.to_dict()

    def update_plan(self, context, plan_id, values):
        plan = _plans.get(plan_id)
        if not plan:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        plan.update(values)
        #TODO update plan
        

    def get_plan_by_id(self, context, plan_id):
        plan = _plans.get(plan_id)
        if not plan:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        return plan.to_dict()

    def get_plans(self, context, search_opts=None):
        plan_list = []
        for p in _plans.values():
            plan_list.append(p.to_dict())
        return plan_list

    def delete_plan(self, context, plan_id):
        plan = _plans.get(plan_id)
        if not plan:
            LOG.error('The plan %s could not be found', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        plan.delete()
        _plans.pop(plan_id, None)
        #TODO database
    
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
                         context.project_id, context.user_id)

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
        new_plan.update({'plan_status': plan_status.AVAILABLE,
                        'expire_at': expire_time})
        
        _plans[plan_id] = new_plan
        
        LOG.debug("Create plan by template finished.")
        
        return new_plan.to_dict()
    
    def _replace_res_id(self, resources):
        new_res = {}
        if isinstance(resources, dict):
            for v in resources.values():
                if isinstance(v, resource.Resource):
                    new_res[v.name] = v
                elif isinstance(v, resource.ResourceDependency):
                    new_res[v.name_in_template] = v
        return new_res
    
