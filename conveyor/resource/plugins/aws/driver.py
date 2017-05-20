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

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.i18n import _LE
from conveyor.resource.plugins import driver

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class AwsDriver(driver.BaseDriver):
    def __init__(self):
        super(AwsDriver, self).__init__()

    def reset_resources(self, context, resources):
        self._handle_resources_after_clone(context, resources)

    def handle_server_after_clone(self, context, resource, resources):
        extra_properties = resource.get('extra_properties', {})
        vm_state = extra_properties.get('vm_state')
        server_id = extra_properties.get('id')
        self._handle_volume_for_vm_after_clone(context,
                                               resource,
                                               resources)
        if vm_state != 'stopped':
            self.compute_api.stop_server(context, server_id)

    def _handle_volume_for_vm_after_clone(self, context,
                                          server_resource, resources):
        bdms = server_resource['properties'].get('block_device_mapping_v2',
                                                 [])
        vgw_id = server_resource.get('extra_properties', {}).get('gw_id')
        sys_clone = server_resource.get('extra_properties', {}) \
                                   .get('sys_clone')
        for bdm in bdms:
            volume_key = bdm.get('volume_id', {}).get('get_resource')
            boot_index = bdm.get('boot_index')
            device_name = bdm.get('device_name')
            volume_res = resources.get(volume_key)
            volume_id = volume_res.get('extra_properties', {}) \
                                  .get('id')
            vgw_url = volume_res.get('extra_properties', {}) \
                                .get('gw_url')
            vgw_ip = vgw_url.split(':')[0]
            if not sys_clone and boot_index in ['0', 0]:
                continue
            try:
                client = birdiegatewayclient.get_birdiegateway_client(
                    vgw_ip, str(CONF.v2vgateway_api_listen_port))
                client.vservices._force_umount_disk("/opt/" + volume_id)
                self.nova_api.detach_volume(context, vgw_id, volume_id)
                self._wait_for_volume_status(context, volume_id,
                                             vgw_id, 'available')
                server_id = server_resource.get('extra_properties', {}) \
                                           .get('id')
                self.nova_api.attach_volume(context, server_id,
                                            volume_id,
                                            device_name)
                self._wait_for_volume_status(context, volume_id,
                                             server_id, 'in-use')
            except Exception as e:
                LOG.error(_LE('Error from handle volume of vm after clone. '
                              'Error=%(e)s'), {'e': e})
