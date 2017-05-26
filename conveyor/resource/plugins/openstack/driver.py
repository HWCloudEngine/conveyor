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

import json

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.clone.resources import common
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.i18n import _LE
from conveyor.i18n import _LW
from conveyor.resource.plugins import driver

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class OpenstackDriver(driver.BaseDriver):
    def __init__(self):
        super(OpenstackDriver, self).__init__()

    def reset_resources(self, context, resources, copy_data):
        self._reset_resources_state(context, resources)
        self._handle_resources_after_clone(context, resources)

    def handle_server_after_clone(self, context, resource, resources):
        self._detach_server_temporary_port(context, resource)
        extra_properties = resource.get('extra_properties', {})
        vm_state = extra_properties.get('vm_state')
        if vm_state == 'stopped':
            self._handle_volume_for_svm_after_clone(context, resource,
                                                    resources)

    def _detach_server_temporary_port(self, context, server_res):
        # Read template file of this plan
        server_id = server_res.get('extra_properties', {}).get('id')
        migrate_port = server_res.get('extra_properties', {}) \
                                 .get('migrate_port_id')
        if server_res.get('extra_properties', {}).get('is_deacidized'):
            if not server_id or not migrate_port:
                return
            try:
                self.compute_api.migrate_interface_detach(context,
                                                          server_id,
                                                          migrate_port)
                LOG.debug("Detach migrate port of server <%s> succeed.",
                          server_id)
            except Exception as e:
                LOG.error("Fail to detach migrate port of server <%s>. %s",
                          server_id, unicode(e))

    def _reset_resources_state(self, context, resources):
        for key, value in resources.items():
            try:
                resource_type = value.get('type')
                resource_id = value.get('extra_properties', {}).get('id')
                if resource_type == 'OS::Nova::Server':
                    vm_state = value.get('extra_properties', {}) \
                                    .get('vm_state')
                    self.compute_api.reset_state(context, resource_id,
                                                 vm_state)
                elif resource_type == 'OS::Cinder::Volume':
                    volume_state = value.get('extra_properties', {}) \
                                        .get('status')
                    self.volume_api.reset_state(context, resource_id,
                                                volume_state)
                elif resource_type == 'OS::Heat::Stack':
                    self._reset_resources_state_for_stack(context, value)
            except Exception as e:
                LOG.warn(_LW('Reset resource state error, Error=%(e)s'),
                         {'e': e})

    def _reset_resources_state_for_stack(self, context, stack_res):
        template_str = stack_res.get('properties', {}).get('template')
        template = json.loads(template_str)

        def _reset_state(template):
            temp_res = template.get('resources')
            for key, value in temp_res.items():
                res_type = value.get('type')
                if res_type == 'OS::Cinder::Volume':
                    vid = value.get('extra_properties', {}).get('id')
                    v_state = value.get('extra_properties', {}).get('status')
                    if vid:
                        self.volume_api.reset_state(context, vid, v_state)
                elif res_type == 'OS::Nova::Server':
                    sid = value.get('extra_properties', {}).get('id')
                    s_state = value.get('extra_properties', {}).\
                        get('vm_state')
                    if sid:
                        self.compute_api.reset_state(context, sid, s_state)
                elif res_type and res_type.startswith('file://'):
                    son_template = value.get('content')
                    son_template = json.loads(son_template)
                    _reset_state(son_template)
        _reset_state(template)

    def handle_stack_after_clone(self, context, resource, resources):
        template_str = resource.get('properties', {}).get('template')
        template = json.loads(template_str)
        self._handle_volume_for_stack_after_clone(context, template)

    def _handle_volume_for_stack_after_clone(self, context, template):
        try:
            resources = template.get('resources')
            for key, res in resources.items():
                res_type = res.get('type')
                if res_type == 'OS::Cinder::Volume':
                    try:
                        if res.get('extra_properties', {}).get(
                                'is_deacidized'):
                            set_shareable = res.get('extra_properties', {}) \
                                               .get('set_shareable')
                            volume_id = res.get('extra_properties', {}) \
                                           .get('id')
                            vgw_id = res.get('extra_properties').get('gw_id')
                            self._detach_volume(context, vgw_id, volume_id)
                            if set_shareable:
                                self.volume_api.set_volume_shareable(context,
                                                                     volume_id,
                                                                     False)
                    except Exception as e:
                        LOG.error(_LE('Error from handle volume '
                                      'of stack after clone.'
                                      'Error=%(e)s'), {'e': e})
                elif res_type and res_type.startswith('file://'):
                    son_template = json.loads(res.get('content'))
                    self._handle_volume_for_stack_after_clone(context,
                                                              son_template)
        except Exception as e:
            LOG.warn('detach the volume %s from vgw %s error,'
                     'the volume not attached to vgw',
                     volume_id, vgw_id)

    def _handle_volume_for_svm_after_clone(self, context,
                                           server_resource, resources):
        bdms = server_resource['properties'].get('block_device_mapping_v2',
                                                 [])
        vgw_id = server_resource.get('extra_properties', {}).get('gw_id')
        for bdm in bdms:
            volume_key = bdm.get('volume_id', {}).get('get_resource')
            boot_index = bdm.get('boot_index')
            device_name = bdm.get('device_name')
            volume_res = resources.get(volume_key)
            try:
                if volume_res.get('extra_properties', {}).\
                        get('is_deacidized'):
                    volume_id = volume_res.get('extra_properties', {}) \
                                          .get('id')
                    vgw_url = volume_res.get('extra_properties', {}) \
                                        .get('gw_url')
                    sys_clone = volume_res.get('extra_properties', {}) \
                                          .get('sys_clone')
                    vgw_ip = vgw_url.split(':')[0]
                    client = birdiegatewayclient.get_birdiegateway_client(
                        vgw_ip, str(CONF.v2vgateway_api_listen_port))

                    if boot_index not in ['0', 0] or sys_clone:
                        client.vservices._force_umount_disk(
                            "/opt/" + volume_id)

                    # if provider cloud can not detcah volume in active status
                    if not CONF.is_active_detach_volume:
                        resouce_common = common.ResourceCommon()
                        self.compute_api.stop_server(context, vgw_id)
                        resouce_common._await_instance_status(context,
                                                              vgw_id,
                                                              'SHUTOFF')
                    if boot_index in ['0', 0]:
                        if sys_clone:
                            self.compute_api.detach_volume(context, vgw_id,
                                                           volume_id)
                            self._wait_for_volume_status(context, volume_id,
                                                         vgw_id, 'available')
                            self.volume_api.set_volume_shareable(context,
                                                                 volume_id,
                                                                 False)
                    else:
                        self.compute_api.detach_volume(context, vgw_id,
                                                       volume_id)
                        self._wait_for_volume_status(context, volume_id,
                                                     vgw_id, 'available')
                        server_id = server_resource.get('extra_properties',
                                                        {}).get('id')
                        self.compute_api.attach_volume(context, server_id,
                                                       volume_id,
                                                       device_name)
                        self._wait_for_volume_status(context, volume_id,
                                                     server_id, 'in-use')

                    if not CONF.is_active_detach_volume:
                        self.compute_api.start_server(context, vgw_id)
                        resouce_common._await_instance_status(context,
                                                              vgw_id,
                                                              'ACTIVE')
            except Exception as e:
                LOG.error(_LE('Error from handle volume of vm after'
                              ' clone.'
                              'Error=%(e)s'), {'e': e})
