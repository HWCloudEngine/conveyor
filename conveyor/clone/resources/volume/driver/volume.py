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

import random

from oslo.config import cfg

from conveyor.common import log as logging
from conveyor.common import plan_status
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor import exception
from conveyor import volume
from conveyor import compute


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class VolumeCloneDriver(object):
    
    def __init__(self):
        self.cinder_api = volume.API()
        self.compute_api = compute.API()
        self._vgw_dict = None
        self._vgw_index = {}
    
    
    def start_volume_clone(self, context, resource_name, template,
                           trans_data_wait_fun=None,
                           volume_wait_fun=None,
                           set_plan_state=None):
        
        resources = template.get('resources')
        volume_res = resources.get(resource_name)
        volume_id = volume_res.get('id')
        plan_id = template.get('plan_id', None)

        # 1. check instance which dependences this volume in template or not
        # if instance exists in template do not execute copy data step
        is_attached = self._check_volume_attach_instance(resource_name, template)
        if is_attached:
            LOG.debug('Volume clone driver: volume %(id)s, name %(name)s',
                      {'id': volume_id, 'name': resource_name})
            # update plan status
            plan_state = 'DATA_TRANS_FINISHED'
            set_plan_state(context, plan_id, plan_state, plan_status.STATE_MAP)
            return 

        # 2. get volume info
        try:
            volume_info = self.cinder_api.get(context, volume_id)
        except Exception as e:
            LOG.error("Clone volume driver get volume %(id)s error: %(error)s",
                      {'id': volume_id, 'error': e})
            raise exception.VolumeNotFound()
        
        volume_az = volume_info.get('availability_zone')

        # 3. attach volume to gateway vm
        vgw_id, vgw_ip = self._get_next_vgw(volume_az)
        LOG.debug('Clone volume driver vgw info: id: %(id)s,ip: %(ip)s',
                  {'id':vgw_id, 'ip': vgw_ip})
        
        des_dev_name = None
        try:
            attach_resp = self.compute_api.attach_volume(context, vgw_id, volume_id, None)
            if volume_wait_fun:
                volume_wait_fun(context, volume_id, 'in-use')
            des_dev_name = attach_resp._info.get('device')
        except Exception as e:
            LOG.error('Volume clone error: attach volume failed:%(id)s,%(e)s',
                      {'id': volume_id, 'e': e})
            raise exception.VolumeNotAttach(volume_id=volume_id,
                                            seconds=120,
                                            attempts=5)
        
        # 4. copy data
        try:
            result = self._copy_volume_data(context, resource_name, vgw_ip, template, des_dev_name)

            des_gw_ip = result.get('des_ip')
            des_port = result.get('des_port')
            task_ids = result.get('copy_tasks')
            if trans_data_wait_fun:
                trans_data_wait_fun(context, des_gw_ip,
                                    des_port, task_ids,
                                    plan_status.STATE_MAP,
                                    plan_id)
        except Exception as e:
            LOG.error('Volume clone error: copy data failed:%(id)s,%(e)s',
                      {'id': volume_id, 'e': e})
            raise
        finally:
            try:
                # 5. detach volume
                self.compute_api.detach_volume(context, vgw_id, volume_id)
                if volume_wait_fun:
                    volume_wait_fun(context, volume_id, 'available')
            except Exception as e:
                LOG.error('Volume clone error: detach failed:%(id)s,%(e)s',
                          {'id': volume_id, 'e': e})
    
    
    def _copy_volume_data(self, context, resource_name, des_gw_ip, template, dev_name):

        LOG.debug('Clone volume driver copy data start for %s', resource_name)
        resources = template.get('resources')
        volume_res = resources.get(resource_name)
        volume_id = volume_res.get('id')
        volume_ext_properties = volume_res.get('extra_properties')
        
        # 1. get gateway vm conveyor agent service ip and port
        des_gw_port = str(CONF.v2vgateway_api_listen_port)
        
        des_gw_url = des_gw_ip + ':' + des_gw_port
        # data transformer procotol(ftp/fillp)
        data_trans_protocol = CONF.data_transformer_procotol
        data_trans_ports = CONF.trans_ports
        trans_port = data_trans_ports[0]
        # 2. get source cloud gateway vm conveyor agent service ip and port
        src_gw_url = volume_ext_properties.get('gw_url')
        
        src_urls = src_gw_url.split(':')
        
        if len(src_urls) != 2:
            LOG.error("Input source gw url error: %s", src_gw_url)
            msg = "Input source gw url error: " + src_gw_url
            raise exception.InvalidInput(reason=msg)

        src_gw_ip = src_urls[0]
        src_gw_port = src_urls[1]
        
        # 3. get volme mount point and disk format info
        
        if volume_ext_properties:
            src_dev_format = volume_ext_properties.get('guest_format')
            src_mount_point = volume_ext_properties.get('mount_point')
            # volume dev name in system
            src_vol_sys_dev = volume_ext_properties.get('sys_dev_name')
            
            if dev_name:
                des_dev_name = dev_name
            else:
                des_dev_name = src_vol_sys_dev
        
        if not src_dev_format:
            client = birdiegatewayclient.get_birdiegateway_client(src_gw_ip, src_gw_port)
            src_dev_format = client.vservices.get_disk_format(src_vol_sys_dev).get('disk_format')
        
        # if disk does not format, then no data to copy
        if not src_dev_format and  data_trans_protocol == 'ftp':
            rsp = {'volume_id': volume_id,
                    'des_ip': None,
                    'des_port': None,
                    'copy_tasks': None}
            return rsp

        if not src_mount_point:
            client = birdiegatewayclient.get_birdiegateway_client(src_urls[0], src_urls[1])
            src_mount_point = client.vservices.get_disk_mount_point(src_vol_sys_dev).get('mount_point')

        mount_point = []
        task_ids = []
        mount_point.append(src_mount_point)

        # 4. copy data
        client = birdiegatewayclient.get_birdiegateway_client(des_gw_ip, des_gw_port)
        clone_rsp = client.vservices.clone_volume(src_vol_sys_dev,
                                                  des_dev_name,
                                                  src_dev_format,
                                                  mount_point,
                                                  src_gw_url,
                                                  des_gw_url,
                                                  trans_protocol=data_trans_protocol,
                                                  trans_port=trans_port)
            
        task_id = clone_rsp.get('body').get('task_id')
        task_ids.append(task_id)

        rsp = {'volume_id': volume_id,
               'des_ip': des_gw_ip,
               'des_port': des_gw_port,
               'copy_tasks': task_ids}

        LOG.debug('Clone volume driver copy data end for %s', resource_name)
        return rsp
    
    def _get_next_vgw(self, region):
        """ return next available (vgw_id, vgw_ip) given region. """
        if region not in self._vgw_index:
            if self._vgw_dict is None:
 
                try:
                    vgw_str = '{' + CONF.vgw_info + '}'
                    self._vgw_dict = eval(vgw_str)
                except Exception as e:
                    LOG.error('read the vgw info error: %s', e)
                    raise
                self._vgw_id = dict([(_r, list(v))
                                     for _r, v in self._vgw_dict.items()
                                     ]
                                    )
            self._vgw_index[region] = random.randint(
                0, len(self._vgw_id[region])-1
            )
        else:
            self._vgw_index[region] = (self._vgw_index[region] + 1) % \
                len(self._vgw_id[region])
        idx = self._vgw_index[region]
        vgw_id = self._vgw_id[region][idx]
        return vgw_id, self._vgw_dict[region][vgw_id]
    
    def _check_volume_attach_instance(self, resource_name, template):

        # 1. Get all server resource info in template,
        # and check each server BDM for containing this volume or not
        LOG.debug('Volume clone start: check volume attached vm exist.')
        resources = template.get('resources')
        for key, res in resources.items():
            res_type = res.get('type')
            if 'OS::Nova::Server' == res_type:
                properties = res.get('properties')
                volumes = properties.get('block_device_mapping_v2')
                if not volumes:
                    continue

                for volume in volumes:
                    vol_name = volume.get('volume_id')
                    if isinstance(vol_name, dict):
                        vol_res_name = vol_name.get('get_resource')
                        if vol_res_name == resource_name:
                            LOG.debug('Volume clone end: volume attached vm exist.')
                            return True
        LOG.debug('Volume clone end: volume attached vm not exist.')
        return False
