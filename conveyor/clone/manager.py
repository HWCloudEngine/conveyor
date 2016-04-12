# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import copy

from oslo.config import cfg
import oslo.messaging as messaging
from conveyor.common import importutils

from conveyor.common import log as logging
from conveyor.i18n import _, _LE, _LI, _LW

from conveyor import manager
from conveyor import volume 
from conveyor import compute
from conveyor import network
from conveyor.clone import rpcapi
from conveyor.resource import api as resource_api
from conveyor.resource import resource
from conveyor import exception
from conveyor.common import excutils
import yaml

from conveyor import heat
from conveyor.common import loopingcall
from conveyor.common import uuidutils
from conveyor.common import plan_status
from novaclient import exceptions as novaclient_exceptions
from neutronclient.common import exceptions as neutronclient_exceptions
resource_from_dict = resource.Resource.from_dict

birdie_opts = [
    cfg.DictOpt('migrate_net_map',
    default={
            },
    help='map of migrate net id of different az'),
    cfg.IntOpt('v2vgateway_api_listen_port',
               default=8899,
               help='Host port for v2v gateway api')
    ]

manager_opts = [
                cfg.ListOpt('resource_managers',
                default=[
                  'instance=conveyor.clone.instances.manager.CloneManager',
                  ],
                help='DEPRECATED. each resource manager class path.'),]
CONF = cfg.CONF
CONF.register_opts(manager_opts)
CONF.register_opts(birdie_opts)

LOG = logging.getLogger(__name__)

template_file_dir = '/tmp/'

template_skeleton = '''
heat_template_version: 2013-05-23
description: Generated template
parameters:
resources:
'''

add_destination_res_type =['OS::Nova::Server' , 'OS::Cinder::Volume']

RESOURCE_MAPPING={'OS::Neutron::Net': 'network',
                  'OS::Neutron::Subnet':'subnet',
                  'OS::Neutron::Port':'port',
                  'OS::Neutron::Router': 'router',
                  'OS::Neutron::SecurityGroup': 'securitygroup',
                  'OS::Cinder::VolumeType': 'volumeType',
                  'OS::Cinder::Volume': 'volume',
                  'OS::Nova::Flavor': 'flavor',
                  'OS::Nova::KeyPair': 'keypair',   
                  'OS::Nova::Server': 'instance'}


STATE_MAP = {
    'CREATE_IN_PROGRESS': 'cloning',
    'CREATE_COMPLETE': 'finished',
    'CREATE_FAILED': 'error',
}



def manager_dict_from_config(named_manager_config, *args, **kwargs):
    ''' create manager class by config file, and set key with class'''
    manager_registry = dict()

    for manager_str in named_manager_config:
        manager_type, _sep, manager = manager_str.partition('=')
        manager_class = importutils.import_class(manager)
        manager_registry[manager_type] = manager_class(*args, **kwargs)

    return manager_registry


class CloneManager(manager.Manager):
    """Manages the clone resources from clone to destruction."""

    target = messaging.Target(version='1.18')

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        
        self.clone_managers = manager_dict_from_config(
            CONF.resource_managers, self)
        self.volume_api = volume.API()
        self.compute_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()
        self._last_host_check = 0
        self._last_bw_usage_poll = 0
        self._bw_usage_supported = True
        self._last_bw_usage_cell_update = 0

        self._resource_tracker_dict = {}
        self._syncs_in_progress = {}
        self.resource_api = resource_api.ResourceAPI()
        super(CloneManager, self).__init__(service_name="clone",
                                             *args, **kwargs)


    def start_template_clone(self, context, template):
        '''here control all resources to distribute, and rollback after error occurring '''
        
        LOG.debug("Clone resources start in clone manager")
        
        #(1. TODO: resolute template,and generate the dependences topo) 
        #(2.TODO: generate TaskFlow according to dependences topo(first, execute leaf node resource))
        
        #1. remove the self-defined keys in template to generate heat template
        stack_template = template['template']
        resources = stack_template['resources']
        #copy resources info in order to retain self-defined info
        src_template = copy.deepcopy(stack_template)
        
        #remove the self-defined keys in template 
        for key, res in resources.items():
            if 'extra_properties' in res:
                res.pop('extra_properties')
                
        #2. call heat create stack interface
        plan_id = template.get('plan_id')
        disable_rollback = template.get('disable_rollback') or True
        stack_name = 'stack-' + uuidutils.generate_uuid()
        stack_kwargs = dict(stack_name=stack_name,
                            disable_rollback=disable_rollback,
                            template=stack_template)
        try:
            stack = self.heat_api.create_stack(context, **stack_kwargs)
            LOG.debug("Create stack info: %s", stack)
        except Exception as e:
            LOG.debug(("Deploy plan %(plan_id)s, with stack error %(error)s."),
                      {'plan_id': plan_id, 'error': e})
            
            raise exception.PlanDeployError(plan_id=plan_id)     
        #3. update plan info in plan table
        values = {}
        stack_info = stack.get('stack')
        values['stack_id'] = stack_info['id']
        self.resource_api.update_plan(context, plan_id, values)
          
        #4. check stack status and update plan status
        def _wait_for_boot():
            values = {}
            """Called at an interval until the resources are deployed ."""
            stack = self.heat_api.get_stack(context, stack_info['id'])
            state = stack.stack_status
            values['plan_status'] = STATE_MAP.get(state)
            
            #update plan status
            self.resource_api.update_plan(context, plan_id, values)
            
            #update plan task status
            self._update_plan_task_status(context, plan_id, stack_info['id'])
            
            if state in ["CREATE_COMPLETE", "CREATE_FAILED"]:
                LOG.info("Plane deployed: %s.", state)                
                raise loopingcall.LoopingCallDone()
                               
        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_boot)
        timer.start(interval=0.5).wait()
        #5. after stack creating success,  start copy data and other steps
        #5.1 according to resource type get resource manager, then call this manager clone template function
        
        src_resources = src_template.get("resources")
        LOG.debug("After pop self define info, resources: %s", src_resources)
        for key, resource in src_resources.items():
            res_type = resource['type']
            
            #5.2 resource create successful, get resource ID, and add to resource
            heat_resource = self.heat_api.get_resource(context, stack_info['id'], key)
            LOG.debug("Heat create resource info:  %s", heat_resource)
            resource['id'] = heat_resource.physical_resource_id
            src_template['stack_id'] = stack_info['id']
            #5.3 call resource manager clone fun
            manager_type = RESOURCE_MAPPING.get(res_type)
            if not manager_type:
                continue
            rs_maganger = self.clone_managers.get(manager_type)
            if not rs_maganger:
                continue
            rs_maganger.start_template_clone(context, key, src_template)
        
        LOG.debug("Clone resources end in clone manager")
        
    def export_clone_template(self, context, id, clone_element):
        
        LOG.debug("export clone template start in clone manager")
        
        # get migrate net map
        migrate_net_map = CONF.migrate_net_map
        
        #get plan
        plan = self.resource_api.get_plan_by_id(context, id)
        
        if not plan:
            LOG.error('get plan %s failed' %id)
            
        expire_time = plan.get('expire_at')
        
        plan_type = plan.get('plan_type')
        
        resource_map = plan.get('original_resources')
        
        for key, value in resource_map.items():
            resource_map[key]  = resource_from_dict(value)
   
        # add migrate port
        if resource_map:
            try:
                self._add_extra_properties_for_servers(context,resource_map,migrate_net_map)
            except Exception:   
                with excutils.save_and_reraise_exception():
                    LOG.exception('add migrate port for server in this plan %s failed ' %id)
        # merge the user param
        if clone_element:
            for element in clone_element:
                element_id = element.get('res_id')
                resource = resource_map.get(element_id)
                if resource:
                    element.pop('res_id')
                    if element.get('id'):
                        resource.id = element.get('id')
                        element.pop('id')
                    if resource.type == 'OS::Neutron::SecurityGroup':
                        element.pop('type')
                        for key, value in element.items():
                            if key == 'security_group_rules':
                                rules = self._build_rules(value)
                                resource.properties['rules'] = rules
                            else:
                                resource.properties[key] = value       
                    else:
                        element.pop('type')
                        for key, value in element.items():
                            resource.properties[key] = value
            resource_map_new = {}              
            for key, value in resource_map.items():
                resource_map_new[key] = value.to_dict()  
            LOG.debug('the resourcemap after update is %s', resource_map_new)
            #write  back the updated_resource 
            self.resource_api.update_plan(context, id, {'updated_resources':resource_map_new,
                                               'plan_status':plan_status.AVAILABLE})  
        else:
            self.resource_api.update_plan(context, id, {'plan_status':plan_status.AVAILABLE})       
        #create template
        self._format_template(resource_map, id, expire_time, plan_type) 
        LOG.debug("export clone template end in clone manager")
        return  resource_map, expire_time
    
    
    def _format_template(self,resource_map, id, expire_time, plan_type):   
        try:
            f = open(template_file_dir + id,'w+')
            resources = resource_map.values()
            template = yaml.load(template_skeleton)
            template['resources'] = {}
            template['parameters'] = {}
            template['expire_time'] = expire_time
            template['plan_type'] = plan_type
            # add expire_time
            for resource in resources:
                template['resources'].update(resource.template_resource)
                template['parameters'].update(resource.template_parameter)
            yaml.safe_dump(template, f, default_flow_style=False)
        except Exception as e:
            LOG.error('format template failed,the exception is %s' % e.message)
            
    def _build_rules(self, rules):
        brules = []
        for rule in rules:
            if rule['protocol'] == 'any':
                del rule['protocol']
            rg_id = rule['remote_group_id']
            if rg_id is not None:
                rule['remote_mode'] = "remote_group_id"
                if rg_id == rule['security_group_id']:
                    del rule['remote_group_id']
            if rule.get('tenant_id'):
                del rule['tenant_id']
            if rule.get('tenant_id'):
                del rule['id']
            if rule.get('security_group_id'):
                del rule['security_group_id']
            rule = dict((k, v) for k, v in rule.items() if v is not None)
            brules.append(rule)
        return brules        
        
    def _add_extra_properties_for_servers(self,context,resource_map,migrate_net_map):
        for key, value in resource_map.items():
            resource_type = value.type
            if resource_type == 'OS::Nova::Server':
                server_properties = value.properties
                # get the availability_zone of server
                server_az = server_properties.get('availability_zone')
                if not server_az:
                    LOG.error('can not get the availability_zone of server %s' %value.id)
                    raise exception.AvailabilityZoneNotFound(server_uuid=value.id)
                migrate_net_id = migrate_net_map.get(server_az)
                if not migrate_net_id:
                    LOG.error('can not get the migrate net of server %s' %value.id)
                    raise exception.NoMigrateNetProvided(server_uuid=value.id)
                # attach interface
                server_id = value.id
                obj = self.compute_api.interface_attach(context,server_id, migrate_net_id, None, None)
                interface_attachment = obj._info
                if interface_attachment:
                    LOG.debug('the interface attachment info is %s ' %str(interface_attachment))
                    migrate_fix_ip = interface_attachment.get('fixed_ips')[0].get('ip_address')
                    migrate_port_id = interface_attachment.get('port_id')
                    gw_url =  migrate_fix_ip + ':' + str(CONF.v2vgateway_api_listen_port)
                    extra_properties ={}
                    extra_properties['gw_url'] = gw_url
                    extra_properties['migrate_port_id'] = migrate_port_id
                    value.extra_properties.update(extra_properties)
                    
    def clone(self,context, id, destination, update_resources):
        LOG.debug("execute clone plan in clone manager")
        #call export_clone_template
        update_resources_clone = copy.deepcopy(update_resources)
        resource_map, expire_time = self.export_clone_template(context, id, update_resources_clone)
        resource_callback_map = {'OS::Nova::Flavor': self.compute_api.get_flavor,
                                'OS::Neutron::Net': self.neutron_api.get_network,
                                'OS::Neutron::SecurityGroup': self.neutron_api.get_security_group,
                                'OS::Neutron::Subnet': self.neutron_api.get_subnet,
                                'OS::Nova::KeyPair': self.compute_api.get_keypair,
                                'OS::Neutron::Router': self.neutron_api.get_router,
                                'OS::Neutron::RouterInterface': self.neutron_api.get_port,
                                'OS::Cinder::VolumeType': self.volume_api.get_volume_type
                                }
        description_map =  {    'OS::Nova::Flavor': 'Flavor description',
                                'OS::Neutron::Net' : 'Network description',
                                'OS::Neutron::SecurityGroup': 'Security group description',
                                'OS::Neutron::Subnet': 'Subnet description',
                                'OS::Neutron::Port': 'Port description',
                                'OS::Nova::KeyPair': 'KeyPair description',
                                'OS::Neutron::Router': 'Router description',
                                'OS::Neutron::RouterInterface': 'RouterInterface description',
                                'OS::Cinder::VolumeType':'VolumeType description'
                         }
       
        #change az for volume server
        for key, value in resource_map.items():
            resource_type = value.type 
            if resource_type in add_destination_res_type:
                value.properties['availability_zone'] = destination 
                
        resources = resource_map.values()
        template = yaml.load(template_skeleton)
        template['resources'] = template_resource = {}
        template['parameters'] = {}
        template['expire_time'] = expire_time
        # add expire_time
        for resource in resources:
            template['resources'].update(resource.template_resource)
            template['parameters'].update(resource.template_parameter)
        
        for key in list(template_resource):
            # key would be port_0, subnet_0, etc...
            resource = template_resource[key]
            
            if resource['type'] == 'OS::Neutron::Port':
                _update_found = False
                for _update_r in update_resources or []:
                    if _update_r['type'] == resource['type'] and _update_r['res_id'] == key:
                        _update_found = True
                for _fix_ip in  resource.get('properties', {}).get('fixed_ips', []):
                    if not _update_found or not _fix_ip.get('ip_address'):
                        _fix_ip.pop('ip_address', None)
            cb = resource_callback_map.get(resource['type'])
            if cb:
                try:
                    resource_id = resource_map[key].id
                    cb(context, resource_id)
                    LOG.debug(" resource %s exists", key)
                    # add parameters into template if exists
                    template['parameters'][key] = {
                            'default': resource_id,
                            'description': description_map[resource['type']],
                            'type': 'string'
                    }
                    def _update_resource(r_list):
                        if type(r_list) not in (tuple, list):
                            r_list = [r_list]
                        for r in r_list:
                            if type(r) is dict:
                                for _k in list(r):                               
                                    if _k == 'get_resource':
                                        if r[_k] == key:
                                            r.pop(_k)
                                            r['get_param'] = key
                                    else:
                                        _update_resource(r[_k])

                    _update_resource(template_resource)
                    template_resource.pop(key)
                except novaclient_exceptions.NotFound, neutronclient_exceptions.NotFound:
                    pass
        template = { "template":{
                      "heat_template_version": '2013-05-23',
                      "description": "clone template" , 
                      "parameters": template['parameters'],
                      "resources": template_resource
                    },
                    "plan_id":id
                    }
        LOG.debug(" the template is  %s ", template)
               
        self.start_template_clone(context, template)
        
        def _wait_for_boot():
            """Called at an interval until the plan status finished"""
            plan = self.resource_api.get_plan_by_id(context, id)
            LOG.debug("Get stack info: %s", plan)
            status =plan.get('plan_status')    
            if status in [plan_status.FINISHED, plan_status.ERROR]:
                LOG.info("Plan status: %s.", status)                
                raise loopingcall.LoopingCallDone()
                               
        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_boot)
        timer.start(interval=1).wait()
                
        # after finish the clone plan ,detach migrate port
        self._clear_migrate_port(context, resource_map)
                            
    def _clear_migrate_port(self,context,resource_map): 
        for key, value in resource_map.items():
            resource_type = value.type
            if resource_type == 'OS::Nova::Server':    
                server_id = value.id 
                extra_properties = value.extra_properties 
                if extra_properties:
                    migrate_port_id = extra_properties.get('migrate_port_id')
                    if migrate_port_id:
                        try:
                            self.compute_api.interface_detach(context,server_id, migrate_port_id) 
                        except Exception as e:
                            LOG.warning('detach the interface %s from server %s error,the exception is %s'
                                         %(migrate_port_id, server_id, e.message))
    
    def _update_plan_task_status(self, context, plan_id, stack_id):
        
        try:
            events = self.heat_api.events_list(context, stack_id)
        except Exception as e:
            raise exception.V2vException(message=e)
        
        if not events:
            return
        
        event = events[0]
        
        res_name = event.resource_name
        res_status = event.resource_status
        
        res_event = res_name + ": " + res_status
        
        values = {}
        values['task_status'] = res_event
        
        try:
            self.resource_api.update_plan(context, plan_id, values)
        except Exception as e:
            LOG.debug("Update plan %(plan_id) task status error:%(error)s",
                      {'plan_id': plan_id, 'error': e})
            raise exception.PlanUpdateException
