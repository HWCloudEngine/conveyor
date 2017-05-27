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

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.clone.resources import common
from conveyor import compute
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor import exception
from conveyor import heat
from conveyor import network
from conveyor import volume

from conveyor.i18n import _LE
from conveyor.resource import api as resource_api

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseDriver(object):
    def __init__(self):
        self.volume_api = volume.API()
        self.compute_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()
        self.resource_api = resource_api.ResourceAPI()

    def _handle_resources_after_clone(self, context, resources):
        for key, res in resources.items():
            if res['type'] == 'OS::Nova::Server':
                self.handle_server_after_clone(context, res, resources)
            elif res['type'] == 'OS::Heat::Stack':
                self.handle_stack_after_clone(context, res, resources)
            elif res['type'] == 'OS::Cinder::Volume':
                self.handle_volume_after_clone(context, res, key, resources)

    def reset_resources(self, context, resources):
        raise NotImplementedError()

    def handle_server_after_clone(self, context, resource, resources):
        raise NotImplementedError()

    def handle_volume_after_clone(self, context, resource,
                                  resource_name, resources):
        clone_along_with_vm = False
        for k, v in resources.items():
            if v['type'] == 'OS::Nova::Server':
                for p in v['properties'].get('block_device_mapping_v2', []):
                    volume_key = p.get('volume_id', {}).get('get_resource')
                    if volume_key and resource_name == volume_key:
                        clone_along_with_vm = True
                        break
            if clone_along_with_vm:
                break
        if not clone_along_with_vm:
            self._handle_dep_volume_after_clone(context, resource)

    def handle_stack_after_clone(self, context, resource, resources):
        raise NotImplementedError()

    def _handle_dep_volume_after_clone(self, context, resource):
        volume_id = resource.get('extra_properties', {}).get('id')
        if not resource.get('extra_properties', {}).get('copy_data'):
            return
        if resource.get('extra_properties', {}).get('is_deacidized'):
            extra_properties = resource.get('extra_properties', {})
            vgw_id = extra_properties.get('gw_id')
            if vgw_id:
                try:
                    mount_point = resource.get('extra_properties', {}) \
                                          .get('mount_point')
                    if mount_point:
                        vgw_url = resource.get('extra_properties', {}) \
                                          .get('gw_url')
                        vgw_ip = vgw_url.split(':')[0]
                        client = birdiegatewayclient.get_birdiegateway_client(
                            vgw_ip, str(CONF.v2vgateway_api_listen_port))
                        client.vservices._force_umount_disk(
                            "/opt/" + volume_id)

                    # if provider cloud can not detach volume in active status
                    if not CONF.is_active_detach_volume:
                        resouce_common = common.ResourceCommon()
                        self.compute_api.stop_server(context, vgw_id)
                        resouce_common._await_instance_status(context,
                                                              vgw_id,
                                                              'SHUTOFF')
                    self.compute_api.detach_volume(context,
                                                vgw_id,
                                                volume_id)
                    self._wait_for_volume_status(context, volume_id, vgw_id,
                                                 'available')

                    if not CONF.is_active_detach_volume:
                        self.compute_api.start_server(context, vgw_id)
                        resouce_common._await_instance_status(context,
                                                              vgw_id,
                                                              'ACTIVE')
                except Exception as e:
                    LOG.error(_LE('Error from handle volume of '
                                  'vm after clone. Error=%(e)s'), {'e': e})

    def _wait_for_volume_status(self, context, volume_id, server_id, status):
        volume = self.volume_api.get(context, volume_id)
        volume_status = volume['status']
        start = int(time.time())
        v_shareable = volume['shareable']
        volume_attachments = volume['attachments']
        attach_flag = False
        end_flag = False
        for vol_att in volume_attachments:
            if vol_att.get('server_id') == server_id:
                attach_flag = True
        if status == 'in-use' and attach_flag:
            end_flag = True
        elif status == 'available' and not attach_flag:
            end_flag = True
        if v_shareable == 'false':
            while volume_status != status:
                time.sleep(CONF.check_interval)
                volume = self.volume_api.get(context, volume_id)
                volume_status = volume['status']
                if volume_status == 'error':
                    raise exception.VolumeErrorException(id=volume_id)
                if int(time.time()) - start >= CONF.check_timeout:
                    message = ('Volume %s failed to reach %s status'
                               '(server %s)'
                               'within the required time (%s s).' %
                               (volume_id, status, server_id,
                                CONF.check_timeout))
                    raise exception.TimeoutException(msg=message)
        else:
            while not end_flag:
                attach_flag = False
                time.sleep(CONF.check_interval)
                volume = self.volume_api.get(context, volume_id)
                volume_attachments = volume['attachments']
                for vol_att in volume_attachments:
                    if vol_att.get('server_id') == server_id:
                        attach_flag = True
                if status == 'in-use' and attach_flag:
                    end_flag = True
                elif status == 'available' and not attach_flag:
                    end_flag = True
                if int(time.time()) - start >= CONF.check_timeout:
                    message = ('Volume %s failed to reach %s status'
                               '(server %s)'
                               'within the required time (%s s).' %
                               (volume_id, status, server_id,
                                CONF.check_timeout))
                    raise exception.TimeoutException(msg=message)

    def _detach_volume(self, context, server_id, volume_id):
        self.compute_api.detach_volume(context, server_id,
                                    volume_id)
        self._wait_for_volume_status(context, volume_id, server_id,
                                     'available')

    def _attach_volume(self, context, server_id, volume_id, device):
        self.compute_api.attach_volume(context, server_id, volume_id,
                                    device)
        self._wait_for_volume_status(context, volume_id, server_id,
                                     'in-use')
