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

from conveyor import compute
from conveyor import exception
from conveyor import network
from conveyor import volume

from conveyor.common import plan_status
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient

from conveyor.conveyorheat.api import api as heat

temp_opts = [
             ]

CONF = cfg.CONF
CONF.register_opts(temp_opts)

LOG = logging.getLogger(__name__)


class StackTemplateCloneDriver(object):
    """Manages the running instances from creation to destruction."""

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        self.cinder_api = volume.API()
        self.nova_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()

    def start_template_clone(self, context, resource_name, template,
                             create_volume_wait_fun=None,
                             volume_wait_fun=None,
                             trans_data_wait_fun=None,
                             create_instance_wait_fun=None,
                             port_wait_fun=None):
        LOG.debug("Clone instance %(i)s starting in template %(t)s driver",
                  {'i': resource_name, 't': template})

        # 1. copy data
        result = self._copy_volume_data(
                        context,
                        resource_name,
                        template,
                        trans_data_wait_fun=trans_data_wait_fun,
                        port_wait_fun=port_wait_fun)

        # 2. check data is transforming finished,
        # and refresh clone plan status
        plan_id = template.get('plan_id', None)
        des_gw_ip = result.get('des_ip', None)
        des_port = result.get('des_port', None)
        task_ids = result.get('copy_tasks', None)
        if task_ids and trans_data_wait_fun:
            trans_data_wait_fun(context, des_gw_ip, des_port, task_ids,
                                plan_status.STATE_MAP, plan_id)

        # 3 deatach data port for new intsance
        server_id = result.get('server_id', None)
        port_id = result.get('port_id', None)
        if port_id:
            self.nova_api.interface_detach(context, server_id, port_id)

        LOG.debug("Clone instances end in template driver")

    def start_template_migrate(self, context, resource_name, template,
                               create_volume_wait_fun=None,
                               volume_wait_fun=None,
                               trans_data_wait_fun=None,
                               create_instance_wait_fun=None,
                               port_wait_fun=None):
        LOG.debug("Migrate instance %(i)s starting in template %(t)s driver",
                  {'i': resource_name, 't': template})

        # 1. copy data
        result = self._copy_volume_data(
                        context, resource_name, template,
                        trans_data_wait_fun=trans_data_wait_fun,
                        port_wait_fun=port_wait_fun)

        # 2. check data is transforming finished,
        # and refresh clone plan status
        plan_id = template.get('plan_id', None)
        des_gw_ip = result.get('des_ip')
        des_port = result.get('des_port')
        task_ids = result.get('copy_tasks')
        if trans_data_wait_fun:
            trans_data_wait_fun(context, des_gw_ip, des_port, task_ids,
                                plan_status.MIGRATE_STATE_MAP, plan_id)

        # 3 deatach data port for new intsance
        server_id = result.get('server_id')
        port_id = result.get('port_id')
        if port_id:
            self.nova_api.interface_detach(context, server_id, port_id)

        LOG.debug("Migrate instance end in template driver")

    def _copy_volume_data(self, context, resource_name, template,
                          trans_data_wait_fun=None, port_wait_fun=None):
        '''copy volumes in template data'''
        resources = template.get('resources')
        instance = resources.get(resource_name)
        # 2. get server info
        server_id = instance.get('id')
        stack_id = template.get('stack_id')

        try:
            server = self.nova_api.get_server(context, server_id)
        except Exception as e:
            LOG.error("Query server %(server_id)s error: %(error)s",
                      {'server_id': server_id, 'error': e})
            raise exception.ServerNotFound(server_id=server_id)

        # 3. get volumes attached to this server
        properties = instance.get('properties')
        ext_properties = instance.get('extra_properties')
        volumes = properties.get('block_device_mapping_v2')
        if not volumes:
            LOG.warn("Clone instance warning: instance does not have volume.")
            rsp = {'server_id': server_id,
                   'port_id': None,
                   'des_ip': None,
                   'des_port': None,
                   'copy_tasks': []}
            return rsp
        bdms = []

        for v_volume in volumes:
            # if volume id is string, this volume is using exist volume,
            # so does not copy data
            vol_res_id = v_volume.get('volume_id')
            if isinstance(vol_res_id, str) or vol_res_id.get('get_param'):
                _msg = "Instance clone warning: volume does not copy data: %s" \
                     % vol_res_id
                LOG.debug(_msg)
                continue
            vol_res_name = v_volume.get('volume_id').get('get_resource')
            sys_clone = ext_properties.get('sys_clone')
            boot_index = v_volume.get('boot_index')
            # 3.1 if do not clone system volume,
            # don't add system volume to bdms
            if not sys_clone and boot_index in [0, '0']:
                continue
            if not ext_properties.get('copy_data'):
                continue
            # 3.2 get volume id
            volume_id = self._get_resource_id(context, vol_res_name, stack_id)
            v_volume['id'] = volume_id
            volume_ext_properties = \
                resources.get(vol_res_name).get('extra_properties')
            if volume_ext_properties:
                v_volume['guest_format'] = \
                    volume_ext_properties.get('guest_format')
                v_volume['mount_point'] = \
                    volume_ext_properties.get('mount_point')
                # volume dev name in system
                vol_sys_dev = volume_ext_properties.get('sys_dev_name')
                # if not None, use it,otherwise use default name
                if vol_sys_dev:
                    v_volume['device_name'] = vol_sys_dev
            bdms.append(v_volume)

        if not bdms:
            return {}
        # 4. create transform data port to new instances
        server_az = server.get('OS-EXT-AZ:availability_zone', None)
        id = server.get('id', None)
        if not server_az:
            LOG.error('Can not get the availability_zone of server %s', id)
            raise exception.AvailabilityZoneNotFound(server_uuid=id)

        migrate_net_map = CONF.migrate_net_map
        migrate_net_id = migrate_net_map.get(server_az, None)

        if migrate_net_id:
            # 4.1 call neutron api create port
            LOG.debug("Instance template driver attach port to instance start")
            net_info = self.nova_api.interface_attach(context, id,
                                                      migrate_net_id,
                                                      port_id=None,
                                                      fixed_ip=None)

            interface_attachment = net_info._info
            if interface_attachment:
                LOG.debug('The interface attachment info is %s ' %
                          str(interface_attachment))
                des_gw_ip = \
                    interface_attachment.get('fixed_ips')[0].get('ip_address')
                port_id = interface_attachment.get('port_id')
            else:
                LOG.error("Instance template driver attach port failed")
                raise exception.NoMigrateNetProvided(server_uuid=id)
        else:
            retrying = 1
            while retrying < 300:
                des_gw_ip = self._get_server_ip(context, server_id)
                if des_gw_ip:
                    break
                retrying += 1
                time.sleep(2)
            port_id = None

        LOG.debug("Instance template driver attach port end: %s", des_gw_ip)
        if not des_gw_ip:
            _msg = "New clone or migrate VM data transformer IP is None"
            raise exception.V2vException(message=_msg)
        des_port = str(CONF.v2vgateway_api_listen_port)
        des_gw_url = des_gw_ip + ":" + des_port

        # data transformer procotol(ftp/fillp)
        data_trans_protocol = CONF.data_transformer_procotol
        data_trans_ports = CONF.trans_ports
        trans_port = data_trans_ports[0]
        src_gw_url = ext_properties.get('gw_url')

        src_urls = src_gw_url.split(':')

        if len(src_urls) != 2:
            LOG.error("Input source gw url error: %s", src_gw_url)
            msg = "Input source gw url error: " + src_gw_url
            raise exception.InvalidInput(reason=msg)
        # 5. request birdiegateway service to clone each volume data
        # record all volume data copy task id
        task_ids = []
        for bdm in bdms:
            # 6.1 query cloned new VM volume name
            # src_dev_name = "/dev/sdc"
            src_dev_name = bdm.get('device_name')
            client = birdiegatewayclient.get_birdiegateway_client(des_gw_ip,
                                                                  des_port)
            des_dev_name = \
                client.vservices.get_disk_name(bdm.get('id')).get('dev_name')
            if not des_dev_name:
                des_dev_name = src_dev_name

            src_dev_format = bdm.get('guest_format')
            # if template does not hava disk format and mount point info
            # query them from conveyor-agent
            if not src_dev_format:
                client = \
                    birdiegatewayclient.get_birdiegateway_client(src_urls[0],
                                                                 src_urls[1])
                d_format = client.vservices.get_disk_format(src_dev_name)
                src_dev_format = d_format.get('disk_format')
            # if volume does not format, this volume not data to transformer
            if not src_dev_format and CONF.data_transformer_procotol == 'ftp':
                continue

            src_mount_point = bdm.get('mount_point')

            if not src_mount_point:
                client = \
                    birdiegatewayclient.get_birdiegateway_client(src_urls[0],
                                                                 src_urls[1])
                m_info = client.vservices.get_disk_mount_point(src_dev_name)
                src_mount_point = m_info.get('mount_point')

            if not src_mount_point and CONF.data_transformer_procotol == 'ftp':
                continue

            mount_point = []
            mount_point.append(src_mount_point)
            LOG.debug('Volume %(dev_name)s disk format is %(disk_format)s'
                      ' and mount point is %(point)s',
                      {'dev_name': src_dev_name,
                       'disk_format': src_dev_format,
                       'point': src_mount_point})

            # get conveyor gateway client to call birdiegateway api
            LOG.debug("Instance template driver transform data start")
            client = birdiegatewayclient.get_birdiegateway_client(des_gw_ip,
                                                                  des_port)
            clone_rsp = client.vservices.clone_volume(
                            src_dev_name,
                            des_dev_name,
                            src_dev_format,
                            mount_point,
                            src_gw_url,
                            des_gw_url,
                            trans_protocol=data_trans_protocol,
                            trans_port=trans_port)
            task_id = clone_rsp.get('body').get('task_id')
            if not task_id:
                LOG.warn("Clone volume %(dev_name)s response is %(rsp)s",
                         {'dev_name': des_dev_name, 'rsp': clone_rsp})
                continue
            task_ids.append(task_id)

        rsp = {'server_id': server_id,
               'port_id': port_id,
               'des_ip': des_gw_ip,
               'des_port': des_port,
               'copy_tasks': task_ids}
        LOG.debug("Instance template driver transform data end")
        return rsp

    def _get_server_ip(self, context, server_id):
        interfaces = self.neutron_api.port_list(context,
                                                device_id=server_id)
        host_ip = None
        for infa in interfaces:
            if host_ip:
                break
            binding_profile = infa.get("binding:profile", [])
            if binding_profile:
                host_ip = binding_profile.get('host_ip')

        return host_ip

    def _get_resource_id(self, context, resource_name, stack_id):

        try:
            LOG.debug("Query stack %(stack)s resource %(name)s id start",
                      {'stack': stack_id, 'name': resource_name})
            heat_resource = self.heat_api.get_resource(context, stack_id,
                                                       resource_name)
            resource_id = heat_resource.physical_resource_id
            LOG.debug("Query stack %(s)s resource %(n)s id end, id is %(id)s",
                      {'s': stack_id, 'n': resource_name, 'id': resource_id})
            return resource_id
        except exception as e:
            LOG.error("Query stack %(s)s resource %(n)s id error: %(error)s",
                      {'s': stack_id, 'n': resource_name, 'error': e})
            return None
