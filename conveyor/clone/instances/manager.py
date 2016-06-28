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

import time
from eventlet import greenthread
from oslo.config import cfg

from conveyor.common import log as logging
from conveyor.i18n import _, _LE, _LI, _LW
from conveyor.common import importutils
from conveyor import exception
from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor.conveyoragentclient.v1 import client as conveyorclient
from conveyor.resource import api as resource_api
from conveyor.brick import base

migrate_manager_opts = [
    cfg.StrOpt('clone_driver',
               default='conveyor.clone.instances.driver.stack_template.StackTemplateCloneDriver',
               help='clone driver'),

    cfg.IntOpt('block_device_allocate_retries',
               default=120,
               help='clone driver'),
    cfg.IntOpt('block_device_allocate_retries_interval',
               default=5,
               help='clone driver'),
                        
    cfg.IntOpt('instance_allocate_retries',
               default=120,
               help='clone driver'),
    cfg.IntOpt('instance_create_retries_interval',
               default=5,
               help='clone driver'),
                        
    cfg.IntOpt('port_allocate_retries',
               default=120,
               help='clone driver'),
    cfg.IntOpt('port_allocate_retries_interval',
               default=1,
               help='clone driver'),
    cfg.IntOpt('allocate_retries',
               default=120,
               help='clone driver'),
    cfg.IntOpt('allocate_retries_interval',
               default=5,
               help='clone driver'),               
]



CONF = cfg.CONF
CONF.register_opts(migrate_manager_opts)
LOG = logging.getLogger(__name__)

class CloneManager(object):
    """Manages the running instances from creation to destruction."""


    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        self.conveyor_cmd = base.MigrationCmd()
        
        self.nova_api = compute.API()
        self.volume_api = volume.API()
        self.network_api = network.API()
        self.resource_api = resource_api.ResourceAPI()
        self.clone_driver = importutils.import_object(CONF.clone_driver)    
        
    def _await_block_device_map_created(self, context, vol_id):
        # TODO(yamahata): creating volume simultaneously
        #                 reduces creation time?
        # TODO(yamahata): eliminate dumb polling
        start = time.time()
        retries = CONF.block_device_allocate_retries
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
            volume = self.volume_api.get(context, vol_id)
            volume_status = volume['status']
            if volume_status not in ['creating', 'downloading']:
                if volume_status != 'available':
                    LOG.warn(_("Volume id: %s finished being created but was"
                               " not set as 'available'"), vol_id)
                return attempt
            greenthread.sleep(CONF.block_device_allocate_retries_interval)
        # NOTE(harlowja): Should only happen if we ran out of attempts
        raise exception.VolumeNotCreated(volume_id=vol_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
  
        
    def _await_volume_status(self, context, vol_id, status):
        # TODO(yamahata): creating volume simultaneously
        #                 reduces creation time?
        # TODO(yamahata): eliminate dumb polling
        start = time.time()
        retries = CONF.block_device_allocate_retries
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
            volume = self.volume_api.get(context, vol_id)
            volume_status = volume['status']
            if volume_status == status:
                LOG.debug(_("Volume id: %s finished being detached"), vol_id)
                return attempt
                
            greenthread.sleep(CONF.block_device_allocate_retries_interval)
            
        # NOTE(harlowja): Should only happen if we ran out of attempts
        if 'available' == status:
            LOG.error(_("Volume id: %s detach failed"), vol_id)
            raise exception.VolumeNotdetach(volume_id=vol_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
        elif 'in-use' == status:
            LOG.error(_("Volume id: %s attach failed"), vol_id)
            raise exception.VolumeNotAttach(volume_id=vol_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
        else:
            raise exception.Error(message="Volume option error.")
    

    def _await_instance_create(self, context, instance_id):
        # TODO(yamahata): creating volume simultaneously
        #                 reduces creation time?
        # TODO(yamahata): eliminate dumb polling
        start = time.time()
        retries = CONF.instance_allocate_retries
        if retries < 0:
            LOG.warn(_LW("Treating negative config value (%(retries)s) for "
                         "'instance_create_retries' as 0."),
                     {'retries': retries})
        # (1) treat  negative config value as 0
        # (2) the configured value is 0, one attempt should be made
        # (3) the configured value is > 0, then the total number attempts
        #      is (retries + 1)
        attempts = 1
        if retries >= 1:
            attempts = retries + 1
        for attempt in range(1, attempts + 1):
            instance = self.nova_api.get_server(context, instance_id)
            instance_status = instance.status
            if instance_status == 'ACTIVE':
                LOG.debug(_("Instance id: %s finished being created"), instance_id)
                return attempt
                
            greenthread.sleep(CONF.instance_create_retries_interval)
            
        # NOTE(harlowja): Should only happen if we ran out of attempts
        raise exception.InstanceNotCreated(instance_id=instance_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
        
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
        
    def _await_data_trans_status(self, context, host, port, task_ids, state_map, plan_id=None):
    
        start = time.time()
        retries = CONF.instance_allocate_retries
        if retries < 0:
            LOG.warn(_LW("Treating negative config value (%(retries)s) for "
                         "'datat_transformer_retries' as 0."),
                     {'retries': retries})
        # (1) treat  negative config value as 0
        # (2) the configured value is 0, one attempt should be made
        # (3) the configured value is > 0, then the total number attempts
        #      is (retries + 1)
        
        #if not volume data to copy
        if not host:
            plan_state = state_map.get('DATA_TRANS_FINISHED')
            values = {}
            values['plan_status'] = plan_state
            values['task_status'] = 'DATA_TRANS_FINISHED'
            self.resource_api.update_plan(context, plan_id, values)
            return 0
                      
        attempts = 1
        if retries >= 1:
            attempts = retries + 1
        for attempt in range(1, attempts + 1):
            #record all volume data transformer task state
            task_states = []
            for task_id in task_ids:
                cls = conveyorclient.get_birdiegateway_client(host, port)
                status = cls.vservices.get_data_trans_status(task_id)
                task_status = status.get('body').get('task_state')
                #if one volume data transformer failed, this clone failed
                if 'DATA_TRANS_FAILED' == task_status:                    
                    plan_state = state_map.get(task_status)
                    values = {}
                    values['plan_status'] = plan_state
                    values['task_status'] = task_status
                    self.resource_api.update_plan(context, plan_id, values)
                    return attempt
                task_states.append(task_status)
            #as long as one volume data does not transformer finished, clone plan state is cloning
            if 'DATA_TRANSFORMING' in task_states:
                    plan_state = state_map.get('DATA_TRANSFORMING')
                    values = {}
                    values['plan_status'] = plan_state
                    values['task_status'] = 'DATA_TRANSFORMING'
                    self.resource_api.update_plan(context, plan_id, values)
            #otherwise, plan state is finished
            else:
                LOG.debug(_("Data transformer finished!"))
                plan_state = state_map.get('DATA_TRANS_FINISHED')
                values = {}
                values['plan_status'] = plan_state
                values['task_status'] = 'DATA_TRANS_FINISHED'
                self.resource_api.update_plan(context, plan_id, values)
                return attempt 
                
            greenthread.sleep(CONF.allocate_retries_interval)
            
        # NOTE(harlowja): Should only happen if we ran out of attempts
        raise exception.InstanceNotCreated(instance_id=task_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
            
            

    def start_template_clone(self, context, resource_name, instance):
        ''' here reset template resource info if the value of key just a link '''
                     
        #1 TODO: Traverse the list of resource, cloning every instance        
        if not instance:
            LOG.error("Resources in template is null")
                    
        #2 TODO: set resource info according to template topo
        #(if the value of key links to other, here must set again)
        try:
            self.clone_driver.start_template_clone(context, resource_name, instance,
                                               create_volume_wait_fun=self._await_block_device_map_created,
                                               volume_wait_fun=self._await_volume_status,
                                               create_instance_wait_fun=self._await_instance_create,
                                               port_wait_fun=self._await_port_status,
                                               trans_data_wait_fun=self._await_data_trans_status)
        
        except Exception as e:
            LOG.error(_LW("Clone vm error: %s"), e)
            _msg='Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)
        
    

    def start_template_migrate(self, context, resource_name, instance):
        ''' here reset template resource info if the value of key just a link '''
                            
        if not instance:
            LOG.error("Resources in template is null")
                    
        #(if the value of key links to other, here must set again)
        try: 
            self.clone_driver.start_template_migrate(context, resource_name, instance,
                                               port_wait_fun=self._await_port_status,
                                               trans_data_wait_fun=self._await_data_trans_status)
        
        except Exception as e:
            LOG.error(_LW("Migrate vm error: %s"), e)
            _msg='Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)
        
