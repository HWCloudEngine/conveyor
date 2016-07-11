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
from conveyor.common import template_format
import json
from conveyor import heat
from conveyor.common import loopingcall
from conveyor.common import uuidutils
from conveyor.common import plan_status
from novaclient import exceptions as novaclient_exceptions
from neutronclient.common import exceptions as neutronclient_exceptions
from conveyor import utils
import functools
from conveyor.brick import base
import time
from eventlet import greenthread
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
resource_from_dict = resource.Resource.from_dict

birdie_opts = [
    cfg.IntOpt('v2vgateway_api_listen_port',
               default=8899,
               help='Host port for v2v gateway api'),
    cfg.IntOpt('check_timeout',
               default=360,
               help='Host port for v2v gateway api'),
    cfg.IntOpt('check_interval',
               default=1,
               help='Host port for v2v gateway api'),
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
        self.conveyor_cmd = base.MigrationCmd()

    def start_template_clone(self, context, template):
        '''here control all resources to distribute, and rollback after error occurring '''
        
        LOG.debug("Clone resources start in clone manager")
        
        #(1. TODO: resolute template,and generate the dependences topo) 
        #(2.TODO: generate TaskFlow according to dependences topo(first, execute leaf node resource))
        
        #1. remove the self-defined keys in template to generate heat template
        src_template = copy.deepcopy(template.get('template'))
        try:
            stack = self._create_resource_by_heat(context, template, plan_status.STATE_MAP)
        except Exception as e:
            LOG.error("Heat create resource error: %s", e)
            return None
        
        stack_info = stack.get('stack')
        #5. after stack creating success,  start copy data and other steps
        #5.1 according to resource type get resource manager, then call this manager clone template function
        
        src_resources = src_template.get("resources")
        plan_id = template.get('plan_id')
        
        if not src_resources:
            values = {}
            values['plan_status'] = plan_status.STATE_MAP.get('DATA_TRANS_FINISHED')
            self.resource_api.update_plan(context, plan_id, values)
            LOG.warning("Clone resource warning: clone resource is empty.")
            return stack_info['id']
                
        LOG.debug("After pop self define info, resources: %s", src_resources)
        try:
            for key, resource in src_resources.items():
                res_type = resource['type']
            
                #5.2 resource create successful, get resource ID, and add to resource
                heat_resource = self.heat_api.get_resource(context, stack_info['id'], key)
                resource['id'] = heat_resource.physical_resource_id
                src_template['stack_id'] = stack_info['id']
                #after step need update plan status
                src_template['plan_id'] = plan_id
                #5.3 call resource manager clone fun
                manager_type = RESOURCE_MAPPING.get(res_type)
                if not manager_type:
                    continue
                rs_maganger = self.clone_managers.get(manager_type)
                if not rs_maganger:
                    values = {}
                    values['plan_status'] = plan_status.STATE_MAP.get('DATA_TRANS_FINISHED')
                    self.resource_api.update_plan(context, plan_id, values)
                    continue
                rs_maganger.start_template_clone(context, key, src_template)
            return stack_info['id']
        except Exception as e:
            LOG.error("Clone resource error: %s", e)
            
            #if clone failed and rollback parameter is true, rollback all resource
            if not template.get('disable_rollback'):
                self.heat_api.delete_stack(context, stack_info['id'])
            return None
            
        return stack_info['id']
        LOG.debug("Clone resources end in clone manager")
        
    def export_clone_template(self, context, id, clone_element):
        
        LOG.debug("export clone template start in clone manager")
        self.resource_api.update_plan(context, id, {'plan_status':plan_status.CREATING})
        
        # get migrate net map
        migrate_net_map = CONF.migrate_net_map
        
        #get plan
        plan = self.resource_api.get_plan_by_id(context, id)
        
        if not plan:
            LOG.error('get plan %s failed' %id)
            raise exception.PlanNotFound(plan_id=id)
            
        expire_time = plan.get('expire_at')
        
        plan_type = plan.get('plan_type')
        
        resource_map = plan.get('updated_resources')
        LOG.debug("the resource_map is %s" %resource_map)
        
        for key, value in resource_map.items():
            resource_map[key]  = resource_from_dict(value)
   
        # add migrate port
        if resource_map:
            try:
                self._add_extra_properties(context, resource_map, migrate_net_map)
            except Exception as e:   
                LOG.exception('add extra_properties for server in this plan %s failed,\
                                 the error is %s ' %(id, e.message)) 
                raise exception.ExportTemplateFailed(id=id, msg=e.message)       
        #create template
        try:
            self._format_template(resource_map, id, expire_time, plan_type) 
        except Exception as e:  
            LOG.error('the generate template of plan %s failed',id)
            raise exception.ExportTemplateFailed(id=id, msg=e.message)
        
        self.resource_api.update_plan(context, id, {'plan_status':plan_status.AVAILABLE})       
        
        LOG.debug("export clone template end in clone manager")
        return  resource_map, expire_time
    
    
    def _format_template(self,resource_map, id, expire_time, plan_type):   
        with open(CONF.plan_file_path + id + '.template','w+') as f:
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
        
    def _add_extra_properties(self, context, resource_map, migrate_net_map):
        for key, value in resource_map.items():
            resource_type = value.type
            if resource_type == 'OS::Nova::Server':
                server_properties = value.properties
                server_extra_properties = value.extra_properties
                server_az = server_properties.get('availability_zone')
                vm_state = server_extra_properties.get('vm_state')
                gw_url = None
                if vm_state == 'stopped':
                    vgw_ip = CONF.vgw_ip_dict.get(server_az)
                    gw_url =  vgw_ip + ':' + str(CONF.v2vgateway_api_listen_port)
                    extra_properties ={}
                    extra_properties['gw_url'] = gw_url
                    value.extra_properties.update(extra_properties)
                    continue
                    
                server_id = value.id
                if migrate_net_map:
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
                        #waiting port attach finished, and can ping this vm
                        self._await_port_status(context, migrate_port_id, migrate_fix_ip)
                else:
                    
                    interfaces = self.neutron_api.port_list(context, device_id=server_id)
                    host_ip = None
                    for infa in interfaces:
                        if host_ip:
                            break
                        binding_profile =infa.get("binding:profile", [])
                        if binding_profile:
                            host_ip = binding_profile.get('host_ip')
                    gw_url =  host_ip + ':' + str(CONF.v2vgateway_api_listen_port)
                    extra_properties ={}
                    extra_properties['gw_url'] = gw_url
                    value.extra_properties.update(extra_properties)
                    #waiting port attach finished, and can ping this vm
                    #self._await_port_status(context, None, host_ip)
    
                block_device_mapping = server_properties.get('block_device_mapping_v2')
                if block_device_mapping:
                    gw_urls = gw_url.split(':') 
                    client = birdiegatewayclient.get_birdiegateway_client(gw_urls[0], gw_urls[1])   
                    for block_device in block_device_mapping:
                        device_name = block_device.get('device_name')
                        volume_name = block_device.get('volume_id').get('get_resource')
                        volume_resource = resource_map.get(volume_name)
                        src_dev_format = client.vservices.get_disk_format(device_name).get('disk_format')
                        src_mount_point = client.vservices.get_disk_mount_point(device_name).get('mount_point')
                        volume_resource.extra_properties['guest_format'] = src_dev_format
                        volume_resource.extra_properties['mount_point'] = src_mount_point
                        
    
    def _handle_volume_for_svm(self, context, resource_map, plan_id):
        # { 'server_0': ('server_0.id, [('volume_0','volume_0.id', '/dev/sdc']) } 
        original_server_volume_map = {}
        for name in resource_map:
            r = resource_map[name]
            if r.type == 'OS::Nova::Server':
                vm_state = r.extra_properties.get('vm_state')
                if vm_state == 'stopped':
                    volume_list = []
                    for p in r.properties.get('block_device_mapping_v2', []):
                        volume_name = p.get('volume_id', {}).get('get_resource')
                        device_name = p.get('device_name')
                        volume_id = resource_map[volume_name].id
                        volume_list.append((volume_name, volume_id, device_name))
                    if volume_list:   
                        original_server_volume_map[name] =( r.id, volume_list)
                        
        if original_server_volume_map:
            for server_key in list(original_server_volume_map):
                server_id,volume_list = original_server_volume_map[server_key]
                undo_mgr = utils.UndoManager()
                def _attach_volume(server_id, volume_id, device ):
                    self.compute_api.attach_volume(context, server_id, volume_id, device)
                    self._wait_for_volume_status(context, volume_id, 'in-use')
                def _detach_volume(server_id, volume_id):
                    self.compute_api.detach_volume(context,server_id, volume_id)
                    self._wait_for_volume_status(context, volume_id, 'available')
                try:   
                    for volume_key, volume_id, device_name in volume_list: 
                        self.compute_api.detach_volume(context, server_id, volume_id) 
                        undo_mgr.undo_with(functools.partial(_attach_volume, server_id, volume_id, device_name))
                        self._wait_for_volume_status(context, volume_id, 'available')
                        server_az = resource_map.get(server_key).properties.get('availability_zone')
                        vgw_id = CONF.vgw_id_dict.get(server_az)
                        self.compute_api.attach_volume(context, vgw_id, volume_id, None)
                        undo_mgr.undo_with(functools.partial(_detach_volume, vgw_id, volume_id))
                        self._wait_for_volume_status(context, volume_id, 'in-use')
                        vgw_ip = CONF.vgw_ip_dict.get(server_az)
                        LOG.debug('begin get info for volume,the vgw ip %s' %vgw_ip)
                        client = birdiegatewayclient.get_birdiegateway_client(vgw_ip, 
                                                                              str(CONF.v2vgateway_api_listen_port))
                        #sys_dev_name = client.vservices.get_disk_name(volume_id).get('dev_name')
                        sys_dev_name = device_name
                        volume_resource = resource_map.get(volume_key)
                        if not sys_dev_name:
                            sys_dev_name = device_name
                            #sys_dev_name = '/dev/vdc'
                        volume_resource.extra_properties['sys_dev_name'] = sys_dev_name
                        guest_format = client.vservices.get_disk_format(sys_dev_name).get('disk_format')
                        if guest_format: 
                            volume_resource.extra_properties['guest_format'] = guest_format
                            mount_point = client.vservices.force_mount_disk(sys_dev_name, "/opt/" + volume_id)
                            volume_resource.extra_properties['mount_point'] = mount_point.get('mount_disk')
                        
                except Exception as e: # TODO, clarify exceptions
                    LOG.exception("Failed migrate server_id %s due to %s, so rollback it.", server_id, str(e.message))
                    LOG.error("START rollback for %s ......", server_id)
                    undo_mgr._rollback()
                    self.resource_api.update_plan(context, plan_id,
                                               {'plan_status':plan_status.ERROR}) 
                #get sys_dev_name disk_format
                
        return original_server_volume_map   
    
    def _handle_volume_after_clone_for_svm(self, context, resource_map, original_server_volume_map): 
        if original_server_volume_map:
            for server_key in list(original_server_volume_map):
                server_id,volume_list = original_server_volume_map[server_key]   
                for volume_key, volume_id, device_name in volume_list: 
                    server_az = resource_map.get(server_key).properties.get('availability_zone')
                    vgw_id = CONF.vgw_id_dict.get(server_az)
                    vgw_ip = CONF.vgw_ip_dict.get(server_az)
                    client = birdiegatewayclient.get_birdiegateway_client(vgw_ip, 
                                                                        str(CONF.v2vgateway_api_listen_port))
                    client.vservices._force_umount_disk("/opt/" + volume_id)
                    self.compute_api.detach_volume(context, vgw_id, volume_id)    
                    self._wait_for_volume_status(context, volume_id, 'available')
                    self.compute_api.attach_volume(context, server_id, volume_id, device_name ) 
                    self._wait_for_volume_status(context, volume_id, 'in-use') 
                    
    def _handle_volume_after_migrate_for_svm(self, context, resource_map, 
                                              original_server_volume_map):
        if original_server_volume_map:
            for server_key in list(original_server_volume_map):
                server_id, volume_list = original_server_volume_map[server_key]   
                for volume_key, volume_id, device_name in volume_list: 
                    server_az = resource_map.get(server_key).properties.get('availability_zone')
                    vgw_id = CONF.vgw_id_dict.get(server_az)
                    vgw_ip = CONF.vgw_ip_dict.get(server_az)
                    client = birdiegatewayclient.get_birdiegateway_client(vgw_ip, 
                                                                        str(CONF.v2vgateway_api_listen_port))
                    client.vservices._force_umount_disk("/opt/" + volume_id)
                    self.compute_api.detach_volume(context, vgw_id, volume_id)    
                    self._wait_for_volume_status(context, volume_id, 'available') 
                    self.volume_api.delete(context,volume_id )
                      
    def clone(self, context, id, destination, update_resources):
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
       
        resources = resource_map.values()
        template = yaml.load(template_skeleton)
        template['resources'] = template_resource = {}
        template['parameters'] = {}
        template['expire_time'] = expire_time
        # add expire_time
        
        # handle volume for stopped volume   
        original_server_volume_map = self._handle_volume_for_svm(context, resource_map, id) 
        
        for resource in resources:
            template['resources'].update(copy.deepcopy(resource.template_resource))
            template['parameters'].update(copy.deepcopy(resource.template_parameter))
            
 
        for key in list(template_resource):
            # key would be port_0, subnet_0, etc...
            resource = template_resource[key] 
            #change az for volume server
            if  resource['type'] in add_destination_res_type:
                resource.get('properties')['availability_zone'] = destination 
                
            if resource['type'] == 'OS::Neutron::Port':
                resource.get('properties').pop('mac_address')
                _update_found = False
                for _update_r in update_resources or []:
                    if _update_r['type'] == resource['type'] and _update_r['res_id'] == key:
                        _update_found = True
                #maybe exist problem if the network not exist       
                for _fix_ip in  resource.get('properties', {}).get('fixed_ips', []):         
                    if not _update_found or not _fix_ip.get('ip_address'):
                        _fix_ip.pop('ip_address', None)
            cb = resource_callback_map.get(resource['type'])
            if cb:
                try:
                    resource_id = resource_map[key].id
                    if not resource_id:
                        continue
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
                except (novaclient_exceptions.NotFound, neutronclient_exceptions.NotFound):
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
               
        stack_id = self.start_template_clone(context, template)  
        if not stack_id:
            LOG.error('clone template error')
            self.resource_api.update_plan(context, id,
                                           {'plan_status':plan_status.ERROR}) 
            self._handle_volume_after_clone_for_svm(context, resource_map, original_server_volume_map) 
            raise exception.PlanCloneFailed(id = id)
        
        def _wait_for_plan_finished(context):
            """Called at an interval until the plan status finished"""
            plan = self.resource_api.get_plan_by_id(context, id)
            LOG.debug("Get stack info: %s", plan)
            status = plan.get('plan_status')    
            if status in [plan_status.FINISHED, plan_status.ERROR]:
                LOG.info("Plan status: %s.", status)                
                raise loopingcall.LoopingCallDone() 
        
        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_plan_finished, context)
        timer.start(interval=0.5).wait()
        # after finish the clone plan ,detach migrate port
        if CONF.migrate_net_map:
            self._clear_migrate_port(context, resource_map)
        
        self._handle_volume_after_clone_for_svm(context, resource_map, original_server_volume_map)
        plan = self.resource_api.get_plan_by_id(context, id) 
        if plan.get('plan_status') == plan_status.ERROR:
            raise exception.PlanCloneFailed(id = id)
        
   
                            
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
            raise exception.PlanUpdateError
    
    def export_migrate_template(self, context, id,):
        LOG.debug("export migrate template start in clone manager")
        
        self.resource_api.update_plan(context, id, {'plan_status':plan_status.CREATING})
        # get migrate net map
        migrate_net_map = CONF.migrate_net_map
        
        #get plan
        plan = self.resource_api.get_plan_by_id(context, id)
        
        if not plan:
            LOG.error('get plan %s failed in export_migrate_template' %id)
            raise exception.PlanNotFound(plan_id=id)
            
        expire_time = plan.get('expire_at')
        
        plan_type = plan.get('plan_type')
        
        resource_map = plan.get('original_resources')
        
        LOG.debug("the resource_map is %s" %resource_map)
        
        for key, value in resource_map.items():
            resource_map[key]  = resource_from_dict(value)
   
        # add migrate port
        if resource_map:
            try:
                self._add_extra_properties(context, resource_map, migrate_net_map)
            except Exception as e:   
                LOG.exception('add extra_properties for server in this plan %s failed,\
                                 the error is %s ' %(id, e.message))
         
        try:
            self._format_template(resource_map, id, expire_time, plan_type) 
        except Exception as e:  
            LOG.error('the generate template of plan %s failed',id)
            raise exception.ExportTemplateFailed(id=id, msg=e)
                   
        self.resource_api.update_plan(context, id, {'plan_status':plan_status.AVAILABLE})       
       
        LOG.debug("export migrate template end in clone manager")
        return  resource_map, expire_time
    
    
    def start_template_migrate(self, context, template):
        '''here control all resources to distribute, and rollback after error occurring '''
        
        LOG.debug("Migrate resources start in clone manager")
        

        src_template = copy.deepcopy(template.get('template'))
        try:
            stack = self._create_resource_by_heat(context, template, plan_status.MIGRATE_STATE_MAP)
        except Exception as e:
            LOG.error("Heat create resource error: %s", e)
            return None
        
        stack_info = stack.get('stack')
        src_resources = src_template.get("resources")
        LOG.debug("After pop self define info, resources: %s", src_resources)
        try:
            for key, resource in src_resources.items():
                res_type = resource['type']
            
                #5.2 resource create successful, get resource ID, and add to resource
                heat_resource = self.heat_api.get_resource(context, stack_info['id'], key)
                resource['id'] = heat_resource.physical_resource_id
                src_template['stack_id'] = stack_info['id']
                src_template['plan_id'] = template.get('plan_id')
                #5.3 call resource manager clone fun
                manager_type = RESOURCE_MAPPING.get(res_type)
                if not manager_type:
                    continue
                rs_maganger = self.clone_managers.get(manager_type)
                if not rs_maganger:
                    continue
                rs_maganger.start_template_migrate(context, key, src_template)
            return stack_info['id']
        except Exception as e:
            LOG.error("Migrate resource error: %s", e)
            
            #if clone failed and rollback parameter is true, rollback all resource
            if not template.get('disable_rollback'):
                self.heat_api.delete_stack(context, stack_info['id'])
            return None
                  
        LOG.debug("Migrate resources end in clone manager")
     
    def _create_resource_by_heat(self, context, template, state_map):
        
        
        #1. remove the self-defined keys in template to generate heat template
        stack_template = template['template']
        resources = stack_template['resources']

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
            values['plan_status'] = state_map.get(state)
            
            #update plan status
            self.resource_api.update_plan(context, plan_id, values)
            
            #update plan task status
            self._update_plan_task_status(context, plan_id, stack_info['id'])
            
            if state in ["CREATE_COMPLETE", "CREATE_FAILED"]:
                LOG.info("Plane deployed: %s.", state)                
                raise loopingcall.LoopingCallDone()
                               
        timer = loopingcall.FixedIntervalLoopingCall(_wait_for_boot)
        timer.start(interval=0.5).wait()
        
        return stack   
    
    def migrate(self, context, id, destination):
        LOG.debug("execute migrate plan in clone manager")
        #call export_clone_template
        
        resource_map, expire_time = self.export_migrate_template(context, id)
        resource_callback_map = {
                                 'OS::Nova::Flavor': self.compute_api.get_flavor,
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
                                'OS::Nova::KeyPair': 'KeyPair description',
                                'OS::Neutron::Router': 'Router description',
                                'OS::Neutron::RouterInterface': 'RouterInterface description',
                                'OS::Cinder::VolumeType':'VolumeType description'
                        }
       
        
        resources = resource_map.values()
        template = yaml.load(template_skeleton)
        template['resources'] = template_resource = {}
        template['parameters'] = {}
        # add expire_time
        template['expire_time'] = expire_time
        
        # handle volume for stopped volume        
        original_server_volume_map = self._handle_volume_for_svm(context, resource_map, id)
        
        for resource in resources:
            template['resources'].update(copy.deepcopy(resource.template_resource))
            template['parameters'].update(copy.deepcopy(resource.template_parameter))
            
        # { 'server_0': ('server_0.id, [('port_0','port_0.id']) } 
        original_server_port_map = {}
        
       
        for name in template_resource:
            r = template_resource[name]
            if r['type'] == 'OS::Nova::Server':
                port_list = []
                for p in r['properties'].get('networks', []):
                    port_name = p.get('port', {}).get('get_resource')
                    port_id = template_resource[port_name].get('extra_properties')['id']
                    net_name = template_resource[port_name].get('properties').\
                                    get('network_id').get('get_resource')
                    net_id =  template_resource[net_name].get('extra_properties')['id']
                    is_exist = self._judge_resource_exist(context, self.neutron_api.get_network, net_id)
                    if is_exist:
                        port_list.append((port_name, port_id))
                original_server_port_map[name] =( r.get('extra_properties')['id'], port_list)
        
             
        #port and fp map {'port_0':[('floatingip_0','floatingip_0.id', 'fix_ip')]
        exist_port_fp_map = {}
        unassociate_floationgip = []
        for key in list(template_resource):
            resource = template_resource[key]
            if resource['type'] == 'OS::Neutron::Port':
                fp_list = []
                for name in list(template_resource):
                    resource_roll = template_resource[name]
                    if resource_roll['type'] == 'OS::Neutron::FloatingIP':
                        if resource_roll['properties'].get('port_id').get('get_resource') == key:
                            floatingip_net_key = resource_roll['properties'].get('floating_network_id',{}).get('get_resource')
                            net_id =  template_resource[floatingip_net_key].get('extra_properties')['id']
                            is_exist = self._judge_resource_exist(context, self.neutron_api.get_network, net_id)
                            if is_exist:
                                fix_ip_index = resource_roll['properties'].get('fixed_ip_address',{}).get('get_attr')[2]
                                fix_ip = resource['properties'].get('fixed_ips')[fix_ip_index].get('ip_address')
                                fp_list.append((name, resource_roll.get('extra_properties')['id'],fix_ip )) 
                                floatingip_id = resource_roll.get('extra_properties')['id']
                                floatingip_info = self.neutron_api.get_floatingip(floatingip_id)
                                floationgip_port_id = floatingip_info.get('port_id')
                                if not floationgip_port_id:
                                    unassociate_floationgip.append(floatingip_id)
                exist_port_fp_map[key] = fp_list 
                
       
                
        for key in list(template_resource):
            # need pop from template ,such as floatingip
            resource = template_resource[key]
            if resource['type'] == 'OS::Neutron::FloatingIP':
                floatingip_net_key = resource['properties'].get('floating_network_id',{}).get('get_resource')
                net_resource = resource_map[floatingip_net_key]
                net_resource_id = net_resource.id
                cb = resource_callback_map.get( net_resource.type)
                if cb:
                    try:
                        if not net_resource_id:
                            continue
                        cb(context, net_resource_id)
                        LOG.debug(" resource %s exists, remove the floatingip", floatingip_net_key) 
                        template_resource.pop(key) 
                        continue   
                    except neutronclient_exceptions.NotFound:
                        pass
            
        for key in list(template_resource):
            # key would be port_0, subnet_0, etc...
            resource = template_resource[key]
            #change az for volume server
            if  resource['type'] in add_destination_res_type:
                resource.get('properties')['availability_zone'] = destination 
                
            cb = resource_callback_map.get(resource['type'])
            if cb:
                try:
                    resource_id = resource_map[key].id
                    if not resource_id:
                        continue
                    cb(context, resource_id)
                    LOG.debug(" resource %s exists", key)  
                    # if the network exists,pop the ip_address
                    if resource['type'] == 'OS::Neutron::Net':
                        for _k in template_resource:
                            _r = template_resource[_k]
                            if _r['type'] == 'OS::Neutron::Port' and \
                                _r['properties'].get('network_id', {}).get('get_resource') == key:
                                _r.get('properties').pop('mac_address')
                                for _f in _r['properties'].get('fixed_ips', []):
                                    _f.pop('ip_address', None)  
                                                   
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
                except (novaclient_exceptions.NotFound, neutronclient_exceptions.NotFound):
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
               
        stack_id = self.start_template_migrate(context, template)
        if not stack_id:
            LOG.error('clone template error')
            self.resource_api.update_plan(context, id,
                                           {'plan_status':plan_status.ERROR}) 
            self._handle_volume_after_migrate_for_svm(context, resource_map, original_server_volume_map)
            raise exception.PlanCloneFailed(id = id)
        # after finish the clone plan ,detach migrate port
        if CONF.migrate_net_map:
            self._clear_migrate_port(context, resource_map)
        
        plan = self.resource_api.get_plan_by_id(context, id) 
        if plan.get('plan_status') == plan_status.ERROR:
            raise exception.PlanMigrateFailed(id=id)
        
        self._realloc_port_floating_ip(context, id, original_server_port_map,exist_port_fp_map,
                                       unassociate_floationgip,resource_map, stack_id)
        
        self._clear(context, resource_map)
        
        self._handle_volume_after_migrate_for_svm(context, resource_map,
                                                   original_server_volume_map)
        
        self.resource_api.update_plan(context, id, {'plan_status':plan_status.FINISHED})  
        
    def _judge_resource_exist(self, context, cb, resource_id):
        is_exist = False
        try:
            cb(context, resource_id)
            LOG.debug('the resource %s exist' %resource_id)
            is_exist = True
        except (novaclient_exceptions.NotFound, neutronclient_exceptions.NotFound):
            pass
        return is_exist
    
    def _realloc_port_floating_ip(self, context, id,
                                   server_port_map, port_fp_map, 
                                   unassociate_floationgip, resource_map, stack_id):
        
        key_dst_heat_resource = {}
        def _get_resource_id_by_key(key):
            r = key_dst_heat_resource.get(key)
            if not r:
                r = self.heat_api.get_resource(context, stack_id, key)
                key_dst_heat_resource[key] = r
            return r.physical_resource_id
        # { 'server_0': ('server_0.id, [('port_0','port_0.id']) } 
        
        for server_key in list(server_port_map):
            server_id,port_list = server_port_map[server_key]
            port_temp_map = {}

            def _associate_fip(fp_id, port_key):
                port_id = port_temp_map[port_key]
                self.neutron_api.associate_floating_ip(context, fp_id, port_id)
            def _delete_port(port_id):
                self.neutron_api.delete_port(context, port_id)
                
            def _detach_port(server_id, port_id):
                self.compute_api.interface_detach(context, server_id, port_id)
                
            def _create_attach_port(server_id, port_key, port_param):
                try:
                    port_id_new = self.neutron_api.create_port(context, {'port': port_params})
                    port_temp_map[port_key] = port_id_new
                except (neutronclient_exceptions.IpAddressInUseClient,
                                    neutronclient_exceptions.MacAddressInUseClient):
                    port_id_new = port_temp_map[port_key]
                self.compute_api.interface_attach(context, server_id, None, port_id_new)

            undo_mgr = utils.UndoManager()
            dst_server_id = _get_resource_id_by_key(server_key)
            
            try:
                for port_key, port_id in port_list:
                    # {'port_0':[('floatingip_0','floatingip_0.id', 'fix_ip')]
                    fp_list = port_fp_map.get(port_key)
                    port_temp_map[port_key] = port_id
                    for (fp_key, fp_id, fix_ip) in fp_list:
                        #disassociate floating_ip 
                        LOG.debug('begin disassociate floating_ip %s' %fp_id)
                        if fp_id not in unassociate_floationgip:   
                            self.neutron_api.disassociate_floating_ip(context, fp_id)
                            undo_mgr.undo_with(functools.partial(_associate_fip, fp_id, port_key))
                        
                    LOG.debug('begin detach interface %s form server %s ' %(port_id, server_id ))    
                    # Note interface_detach will delete the port.
                    self.compute_api.interface_detach(context, server_id, port_id)
                    port_info = resource_map.get(port_key)
                    net_key = port_info.properties.get('network_id').get('get_resource')
                    security_group_list = port_info.properties.get('security_groups')
                    security_group_ids = []
                    for security_group in security_group_list:
                        security_group_key = security_group.get('get_resource')
                        security_group_id =  resource_map.get(security_group_key).id
                        security_group_ids.append(security_group_id)
                    port_params = {'network_id': resource_map.get(net_key).id, 
                                   'mac_address': port_info.properties.get('mac_address'),
                                   'security_groups':security_group_ids,
                                   'admin_state_up':True}                
                    for fix in port_info.properties.get('fixed_ips', []):
                        subnet_key = fix.get('subnet_id', {}).get('get_resource')
                        subnet_id = resource_map.get(subnet_key).id
                        fix_param = {'subnet_id':subnet_id, 'ip_address': fix.get('ip_address')}
                        port_params.setdefault('fixed_ips', []).append(fix_param)

                    # interface_detach rolling back callback
                    undo_mgr.undo_with(functools.partial(_create_attach_port, server_id, port_key, port_params))
                    create_port_attempt = 150
                    for i in range(create_port_attempt):  
                        try:
                            LOG.debug('begin create new port %s', port_params)
                            port_id_new = self.neutron_api.create_port(context, {'port': port_params})
                            LOG.debug(' create new port success the port is %s', port_id_new)
                            port_temp_map[port_key] = port_id_new
                            undo_mgr.undo_with(functools.partial(_delete_port, port_id_new))
                            break
                        except (neutronclient_exceptions.IpAddressInUseClient,
                                        neutronclient_exceptions.MacAddressInUseClient):
                            time.sleep(1)
                            pass
                    if not port_id_new :
                        port_id_new = port_id
                    dst_server_port_id = _get_resource_id_by_key(port_key)
                    LOG.debug('begin detach interface %s from server %s' %(dst_server_port_id,dst_server_id))
                    ## no rolling back for dst server.
                    self.compute_api.interface_detach(context, dst_server_id, dst_server_port_id) 
                    
                    LOG.debug('begin attach interface %s to server %s' %(port_id_new,dst_server_id))   
                    ## no rolling back for dst server.
                    self.compute_api.interface_attach(context, dst_server_id, None, port_id_new)
                    
                    
                    ## no rolling back for dst server.
                    if fp_list:
                        LOG.debug('begin associate floating_ip %s to server %s' %(fp_id,dst_server_id))  
                        self.neutron_api.associate_floating_ip(context, fp_id, port_id_new, fixed_address=fix_ip)
                        undo_mgr.undo_with(functools.partial(self.heat_api.delete_stack, context, stack_id))
                       
            except Exception as e: # TODO, clarify exceptions
                LOG.exception("Failed migrate server_id %s due to %s, so rollback it.", server_id, str(e.message))
                LOG.error("START rollback for %s ......", server_id)
                undo_mgr._rollback()
                self.resource_api.update_plan(context, id,
                                           {'plan_status':plan_status.ERROR}) 
                try: 
                    self.heat_api.delete_stack(context, stack_id)
                except Exception:
                    pass
                LOG.error("END rollback for %s ......", server_id)
                raise exception.PlanMigrateFailed(id=id)
        
            
    def _clear(self,context,resource_map):     
        for key, value in resource_map.items():
            resource_type = value.type 
            if resource_type == 'OS::Nova::Server':
                server_id = value.id
                server = self.compute_api.get_server(context, server_id)
                volume_ids = []  
                if getattr(server, 'os-extended-volumes:volumes_attached', ''):
                    volumes = getattr(server, 'os-extended-volumes:volumes_attached', [])
                    for v in volumes:
                        if v.get('id'):
                            volume_ids.append(v.get('id'))
                self.compute_api.delete_server(context, server_id)
                
                timer = loopingcall.FixedIntervalLoopingCall(self._wait_for_server_termination, context, server_id)
                timer.start(interval=0.5).wait()
                for v_id in volume_ids:
                    self.volume_api.delete(context, v_id)
            
    def download_template(self, context, id):
        try:
             
            with open(CONF.plan_file_path + id + '.template') as f:
                #content = yaml.load(f)
                content = f.read()
                content = template_format.parse(content)
                return {'template':content}
        except IOError:
            LOG.error('the file %s not exist' %CONF.plan_file_path + id)
            raise exception.DownloadTemplateFailed(id=id, msg=IOError.message)
        
    def _wait_for_server_termination(self, context, server_id):
        while True:
            
            try:
                self.compute_api.delete_server(context, server_id)
                server = self.compute_api.get_server(context, server_id)
            except novaclient_exceptions.NotFound:
                LOG.debug('the server %s deleted ' %server_id)
                raise loopingcall.LoopingCallDone() 
    
            server_status = server.status
            if server_status == 'ERROR':
                LOG.debug('the server %s delete failed' %server_id)
                loopingcall.LoopingCallDone() 
                
    def _wait_for_volume_status(self, context, volume_id, status):
        volume = self.volume_api.get(context, volume_id)
        volume_status = volume['status']
        start = int(time.time())

        while volume_status != status:
            time.sleep(CONF.check_interval)
            volume = self.volume_api.get(context, volume_id)
            volume_status = volume['status']
            if volume_status == 'error':
                raise exception.VolumeErrorException(id=volume_id)
            if int(time.time()) - start >= CONF.check_timeout:
                message = ('Volume %s failed to reach %s status (current %s) '
                           'within the required time (%s s).' %
                           (volume_id, status, volume_status,
                            CONF.build_timeout))
                raise exception.TimeoutException(msg = message)

                
    def _await_port_status(self, context, port_id, ip_address):
        # TODO(yamahata): creating volume simultaneously
        #                 reduces creation time?
        # TODO(yamahata): eliminate dumb polling
        start = time.time()
        retries = CONF.port_allocate_retries
        if retries < 0:
            LOG.warn(_LW("Treating negative config value (%(retries)s) for "
                         "'block_device_retries' as 0."),
                     {'retries': retries})
        # (1) treat  negative config value as 0
        # (2) the configured value is 0, one attempt should be made
        # (3) the configured value is > 0, then the total number attempts
        #      is (retries + 1)
        attempts = 1
        if retries >= 1:
            attempts = retries + 1
        for attempt in range(1, attempts + 1):
           
            LOG.debug(_("port id: %s finished being attached"), port_id)
            exit_status = self._check_connect_sucess(ip_address)
            if exit_status:
                return attempt
            else:
                continue
                
            greenthread.sleep(CONF.port_allocate_retries_interval)
            
        # NOTE(harlowja): Should only happen if we ran out of attempts
        raise exception.PortNotattach(port_id=port_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
        
    def _check_connect_sucess(self, ip_address, times_for_check=3, interval=1):
        '''check ip can ping or not'''
        exit_status = False

        for i in range(times_for_check):
            time.sleep(interval)
            exit_status = self.conveyor_cmd.check_ip_connect(ip_address)
            if exit_status:
                break
            else:
                continue

        return exit_status
