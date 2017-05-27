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

from eventlet import greenthread
import functools
import time

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.clone.resources import common
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor import heat
from conveyor.i18n import _LE
from conveyor.i18n import _LW
from conveyor.resource import api as resource_api

from conveyor import compute
from conveyor import exception
from conveyor import network
from conveyor import utils
from conveyor import volume


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


template_skeleton = '''
heat_template_version: 2013-05-23
description: Generated template
parameters:
resources:
'''


class BaseDriver(object):
    def __init__(self):
        self.volume_api = volume.API()
        self.compute_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()
        self.resource_api = resource_api.ResourceAPI()

    def _add_extra_properties(self, context, resource_map,
                              sys_clone, copy_data, undo_mgr):
        for key, value in resource_map.items():
            resource_type = value.type
            if resource_type == 'OS::Nova::Server':
                self.add_extra_properties_for_server(context, value,
                                                     resource_map, sys_clone,
                                                     copy_data, undo_mgr)
            elif resource_type == 'OS::Cinder::Volume':
                self.add_extra_properties_for_volume(context, key,
                                                     value, resource_map,
                                                     sys_clone, copy_data,
                                                     undo_mgr)
            elif resource_type == 'OS::Heat::Stack':
                self.add_extra_properties_for_stack(context, value, undo_mgr)

    def add_extra_properties_for_server(self, context, resource, resource_map,
                                        sys_clone, copy_data, undo_mgr):
        raise NotImplementedError()

    def add_extra_properties_for_stack(self, context, resource, undo_mgr):
        raise NotImplementedError()

    def handle_resources(self, context, plan_id, resource_map, sys_clone,
                         copy_data):
        raise NotImplementedError()

    def add_extra_properties_for_volume(self, context, resource_name,
                                        resource, resource_map,
                                        sys_clone, copy_data, undo_mgr):
        clone_along_with_vm = False
        for name in resource_map:
            r = resource_map[name]
            if r.type == 'OS::Nova::Server':
                for p in r.properties.get('block_device_mapping_v2', []):
                    volume_key = p.get('volume_id', {}).get('get_resource')
                    if volume_key and resource_name == volume_key:
                        clone_along_with_vm = True
                        break
            if clone_along_with_vm:
                break
        if not clone_along_with_vm:
            self._add_extra_properties_for_dep_volume(context, resource,
                                                      copy_data, undo_mgr)

    def _add_extra_properties_for_dep_volume(self, context, resource,
                                             copy_data, undo_mgr):
        volume_id = resource.id
        volume = self.volume_api.get(context, volume_id)
        volume_status = volume['status']
        is_shareable = volume['shareable']
        if volume_status == 'in_use' and is_shareable == 'false':
            error_message = 'the volume is in_use and not shareable'
            raise exception.V2vException(message=error_message)
        else:
            gw_url = resource.extra_properties.get('gw_url')
            if not gw_url:
                az = resource.properties.get('availability_zone')
                gw_id, gw_ip = utils.get_next_vgw(az)
                if not gw_id or not gw_ip:
                    raise exception.V2vException(message='no vgw host found')
                gw_url = gw_ip + ':' + str(CONF.v2vgateway_api_listen_port)
                resource.extra_properties.update({"gw_url": gw_url,
                                                  "gw_id": gw_id})
                resource.extra_properties['is_deacidized'] = True
                new_copy = \
                    resource.extra_properties['copy_data'] and copy_data
                resource.extra_properties.update({'copy_data': new_copy})
                if new_copy:
                    self._handle_dep_volume(context, resource, gw_id, gw_ip,
                                            undo_mgr)

    def _handle_dep_volume(self, context, resource, gw_id, gw_ip, undo_mgr):
        volume_id = resource.id
        LOG.debug('Attach volume %s to gw host %s', volume_id, gw_id)
        # query disk list before attaching (add wanggang)
        client = birdiegatewayclient.get_birdiegateway_client(
            gw_ip,
            str(CONF.v2vgateway_api_listen_port)
        )
        disks = set(client.vservices.get_disk_name().get('dev_name'))

        self.compute_api.attach_volume(context,
                                       gw_id,
                                       volume_id,
                                       None)
        undo_mgr.undo_with(functools.partial(self._detach_volume,
                                             gw_id,
                                             volume_id))
        self._wait_for_volume_status(context, volume_id,
                                     gw_id,
                                     'in-use')

        n_disks = set(client.vservices.get_disk_name().get('dev_name'))

        diff_disk = n_disks - disks
        resource.extra_properties['status'] = 'in-use'
        LOG.debug('Begin get info for volume,the vgw ip %s' % gw_ip)
        client = birdiegatewayclient.get_birdiegateway_client(
            gw_ip,
            str(CONF.v2vgateway_api_listen_port)
        )
        # sys_dev_name = client.vservices.get_disk_name(volume_id).get(
        #                 'dev_name')
        # sys_dev_name = device_name
        # sys_dev_name = attach_resp._info.get('device')
        sys_dev_name = list(diff_disk)[0] if len(diff_disk) >= 1 else None
        LOG.debug("in _handle_dep_volume dev_name = %s", sys_dev_name)
        resource.extra_properties['sys_dev_name'] = sys_dev_name
        guest_format = client.vservices.get_disk_format(sys_dev_name)\
                             .get('disk_format')
        if guest_format:
            resource.extra_properties['guest_format'] = guest_format
            mount_point = client.vservices.force_mount_disk(
                sys_dev_name, "/opt/" + volume_id)
            resource.extra_properties['mount_point'] = mount_point.get(
                'mount_disk'
            )

    def _attach_volume(self, context, server_id, volume_id, device):
        self.compute_api.attach_volume(context, server_id, volume_id,
                                       device)
        self._wait_for_volume_status(context, volume_id, server_id,
                                     'in-use')

    def _detach_volume(self, context, server_id, volume_id):
        self.compute_api.detach_volume(context, server_id,
                                       volume_id)
        self._wait_for_volume_status(context, volume_id, server_id,
                                     'available')

    def _set_volume_shareable(self, context, volume_id, flag):
        self.volume_api.set_volume_shareable(context, volume_id, flag)

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
            LOG.debug("Port id: %s finished being attached", port_id)
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

    def _handle_dv_for_svm(self, context, vol_res, server_id, dev_name,
                           gw_id, gw_ip, undo_mgr):
        volume_id = vol_res.id
        LOG.debug('detach the volume %s form server %s', volume_id, server_id)
        self.compute_api.detach_volume(context, server_id,
                                       volume_id)
        undo_mgr.undo_with(functools.partial(self._attach_volume,
                                             context,
                                             server_id,
                                             volume_id,
                                             dev_name))
        self._wait_for_volume_status(context, volume_id, server_id,
                                     'available')

        client = birdiegatewayclient.get_birdiegateway_client(
            gw_ip,
            str(CONF.v2vgateway_api_listen_port)
        )
        disks = set(client.vservices.get_disk_name().get('dev_name'))

        self.compute_api.attach_volume(context,
                                       gw_id,
                                       volume_id,
                                       None)
        LOG.debug('attach volume %s to gw host %s', volume_id, gw_id)
        undo_mgr.undo_with(functools.partial(self._detach_volume,
                                             context,
                                             gw_id,
                                             volume_id))
        self._wait_for_volume_status(context, volume_id, gw_id,
                                     'in-use')
        n_disks = set(client.vservices.get_disk_name().get('dev_name'))

        diff_disk = n_disks - disks
        LOG.debug('begin get info for volume,the vgw ip %s' % gw_ip)
        client = birdiegatewayclient.get_birdiegateway_client(
            gw_ip, str(CONF.v2vgateway_api_listen_port))
#         sys_dev_name = client.vservices.get_disk_name(volume_id).get(
#             'dev_name')
#         sys_dev_name = device_name
        # sys_dev_name = attach_resp._info.get('device')
        sys_dev_name = list(diff_disk)[0] if len(diff_disk) >= 1 else None
        LOG.debug("dev_name = %s", sys_dev_name)

        vol_res.extra_properties['sys_dev_name'] = sys_dev_name
        guest_format = client.vservices.get_disk_format(sys_dev_name)\
                             .get('disk_format')
        if guest_format:
            vol_res.extra_properties['guest_format'] = guest_format
            mount_point = client.vservices.force_mount_disk(
                sys_dev_name, "/opt/" + volume_id)
            vol_res.extra_properties['mount_point'] = mount_point.get(
                'mount_disk')

    def reset_resources(self, context, resources):
        raise NotImplementedError()

    def _handle_resources_after_clone(self, context, resources):
        for key, res in resources.items():
            if res['type'] == 'OS::Nova::Server':
                self.handle_server_after_clone(context, res, resources)
            elif res['type'] == 'OS::Heat::Stack':
                self.handle_stack_after_clone(context, res, resources)
            elif res['type'] == 'OS::Cinder::Volume':
                self.handle_volume_after_clone(context, res, key, resources)

    def handle_server_after_clone(self, context, resource, resources):
        raise NotImplementedError()

    def handle_stack_after_clone(self, context, resource, resources):
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

    def _handle_dep_volume_after_clone(self, context, resource):
        volume_id = resource.get('extra_properties', {}).get('id')
        if resource.get('extra_properties', {}).get('is_deacidized'):
            extra_properties = resource.get('extra_properties', {})
            vgw_id = extra_properties.get('gw_id')
            if not extra_properties.get('copy_data', True):
                return
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
                    resouce_common = common.ResourceCommon()
                    if not CONF.is_active_detach_volume:
                        # resouce_common = common.ResourceCommon()
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
                    LOG.error(_LE('Error from handle volume of vm after clone.'
                                  'Error=%(e)s'), {'e': e})
