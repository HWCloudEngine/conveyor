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

import functools
import json

from cinderclient import exceptions as cinderclient_exceptions
from novaclient import exceptions as novaclient_exceptions
from oslo_config import cfg
from oslo_log import log as logging

from conveyor import compute
from conveyor.resource.plugins import driver
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor import exception
from conveyor import heat
from conveyor.i18n import _LE
from conveyor import network
from conveyor import utils
from conveyor import volume


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class OpenstackDriver(driver.BaseDriver):
    def __init__(self):
        self.volume_api = volume.API()
        self.compute_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()

    def reset_resources(self, context, resources):
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
                self.nova_api.migrate_interface_detach(context,
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
                    self.nova_api.reset_state(context, resource_id, vm_state)
                elif resource_type == 'OS::Cinder::Volume':
                    volume_state = value.get('extra_properties', {}) \
                                        .get('status')
                    self.cinder_api.reset_state(context, resource_id,
                                                volume_state)
                elif resource_type == 'OS::Heat::Stack':
                    self._reset_resources_state_for_stack(context, value)
            except Exception as e:
                LOG.warn('reset resource state error, error is %s', e.msg)

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
                                self.cinder_api.set_volume_shareable(context,
                                                                     volume_id,
                                                                     False)
                    except novaclient_exceptions.NotFound:
                        LOG.warn('detach the volume %s from vgw %s error,'
                                 'the volume not attached to vgw',
                                 volume_id, vgw_id)
                    except exception.TimeoutException:
                        LOG.error('detach the volume %s from vgw %s error')
                        raise exception.V2vException(
                            'handle volume of stack error')
                elif res_type and res_type.startswith('file://'):
                    son_template = json.loads(res.get('content'))
                    self._handle_volume_for_stack_after_clone(context,
                                                              son_template)
        except cinderclient_exceptions.NotFound:
            LOG.warn('detach the volume %s from vgw %s error,'
                     'the volume not attached to vgw',
                     volume_id, vgw_id)

    def _handle_volume_for_svm_after_clone(self, context,
                                           server_resource, resources):
        bdms = server_resource['properties'].get('block_device_mapping_v2', [])
        vgw_id = server_resource.get('extra_properties', {}).get('gw_id')
        for bdm in bdms:
            volume_key = bdm.get('volume_id', {}).get('get_resource')
            boot_index = bdm.get('boot_index')
            device_name = bdm.get('device_name')
            volume_res = resources.get(volume_key)
            try:
                if volume_res.get('extra_properties', {}).get('is_deacidized'):
                    volume_id = volume_res.get('extra_properties', {}) \
                                          .get('id')
                    vgw_url = volume_res.get('extra_properties', {}) \
                                        .get('gw_url')
                    sys_clone = volume_res.get('extra_properties', {}) \
                                          .get('sys_clone')
                    vgw_ip = vgw_url.split(':')[0]
                    client = birdiegatewayclient.get_birdiegateway_client(
                        vgw_ip, str(CONF.v2vgateway_api_listen_port))
                    client.vservices._force_umount_disk("/opt/" + volume_id)
                    if boot_index in ['0', 0]:
                        if sys_clone:
                            self.nova_api.detach_volume(context, vgw_id,
                                                        volume_id)
                            self._wait_for_volume_status(context, volume_id,
                                                         vgw_id, 'available')
                            self.cinder_api.set_volume_shareable(context,
                                                                 volume_id,
                                                                 False)
                    else:
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
            except novaclient_exceptions.NotFound as e:
                LOG.warn('handle the volume %s after clone error, error is %s',
                         volume_id, e.msg)
                try:
                    volume = self.cinder_api.get(context, volume_id)
                    volume_status = volume['status']
                    shareable = volume['shareable']
                    if volume_status == 'available' or shareable == 'true':
                        self.nova_api.attach_volume(context, server_id,
                                                    volume_id,
                                                    device_name)
                except Exception as e:
                    LOG.debug('try to attach volume %s to server %s failed',
                              volume_id, server_id)
            except novaclient_exceptions.BadRequest as e:
                LOG.warn('handle the volume %s after clone error, error is %s',
                         volume_id, e.msg)
            except exception.TimeoutException:
                LOG.error('detach the volume %s from vgw %s error or attach volume or \
                          attach the volume %s to server %s error')
                raise exception.V2vException('handle independent volume error')
