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


from conveyor.clone.drivers import driver
from conveyor.i18n import _LE

from conveyor import exception
from conveyor import utils

from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class AwsDriver(driver.BaseDriver):
    def __init__(self):
        super(AwsDriver, self).__init__()

    def handle_resources(self, context, plan_id, resource_map, sys_clone,
                         copy_data):
        LOG.debug('Begin handle resources')
        undo_mgr = utils.UndoManager()
        try:
            self._add_extra_properties(context, resource_map, sys_clone,
                                       undo_mgr)
            return undo_mgr
        except Exception as e:
            LOG.error(_LE('Generate template failed, err:%s'), str(e))
            undo_mgr._rollback()
            raise exception.ExportTemplateFailed(id=plan_id, msg=str(e))

    def add_extra_properties_for_server(self, context, resource, resource_map,
                                        sys_clone, copy_data, undo_mgr):
        server_properties = resource.properties
        server_id = resource.id
        server_az = server_properties.get('availability_zone')
        server_extra_properties = resource.extra_properties
        vm_state = server_extra_properties.get('vm_state')
        gw_url = server_extra_properties.get('gw_url')
        if gw_url:
            return
        gw_id, gw_ip = utils.get_next_vgw(server_az)
        gw_url = gw_ip + ':' + str(CONF.v2vgateway_api_listen_port)
        if sys_clone:
            if vm_state != 'stopped':
                self.compute_api.stop_server(context, server_id)
        block_device_mapping = server_properties.get(
            'block_device_mapping_v2')
        if block_device_mapping:
            for block_device in block_device_mapping:
                volume_name = block_device.get('volume_id').get(
                    'get_resource')
                volume_resource = resource_map.get(volume_name)
                boot_index = block_device.get('boot_index')
                dev_name = block_device.get('device_name')
                if boot_index == 0 or boot_index == '0':
                    volume_resource.extra_properties['sys_clone'] = \
                        sys_clone
                    if sys_clone:
                        self._handle_sv_for_vm(context, volume_resource,
                                               server_id, dev_name,
                                               gw_id, gw_ip, undo_mgr)
                self._handle_dv_for_svm(context, volume_resource,
                                        server_id, dev_name,
                                        gw_id, gw_ip, undo_mgr)

    def _handle_sv_for_vm(self, context, vol_res, server_id, dev_name,
                          gw_id, gw_ip, undo_mgr):
        self._handle_dv_for_svm(context, vol_res, server_id,
                                dev_name, gw_id, gw_ip, undo_mgr)
