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

from oslo.config import cfg

from conveyor.common import log as logging
from conveyor.i18n import _, _LE, _LI, _LW
from conveyor import volume 
from conveyor import compute
from conveyor import image as glance_image
from conveyor import exception
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
import time

from conveyor import heat

temp_opts = [
    cfg.StrOpt('data_trans_vm',
               default='',
               help='VM for clone or migrate resource to transform data'),
    cfg.StrOpt('data_trans_vm_host',
               default='',
               help='host ip for v2vgateway service in vm  for clone or migrate resource to transform data'),
    cfg.IntOpt('data_trans_vm_port',
               default='',
               help='port for v2vgateway service in vm  for clone or migrate resource to transform data'),   
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
        self.heat_api = heat.API()
        
    def start_template_clone(self, context, resource_name, template, create_volume_wait_fun=None,
                             volume_wait_fun=None,
                             trans_data_wait_fun=None,
                             create_instance_wait_fun=None,
                             port_wait_fun=None):
        LOG.debug("Clone instance %(instance)s starting in template %(template)s driver",
                  {'instance': resource_name, 'template': template})
        
        resources = template.get('resources')
        instance = resources.get(resource_name)
        #2. get server info
        server_id = instance.get('id')
        try:
            server = self.nova_api.get_server(context, server_id)
        except Exception as e:
            LOG.error("Query server %(server_id)s error: %(error)s",
                      {'server_id': server_id, 'error': e})
            raise exception.ServerNotFound(server_id=server_id)
        
        #3. get volumes attached to this server
        properties = instance.get('properties')
        ext_properties = instance.get('extra_properties')
        volumes = properties.get('block_device_mapping_v2')
        if not volumes:
            LOG.warn("Clone instance warning: instance does not have volume to clone.")
            return
        bdms = []
        
        for volume in volumes:
            vol_res_name = volume.get('volume_id').get('get_resource')
            sys_clone = ext_properties.get('sys_clone')
            bool_index = volume.get('bool_index')
            #3.1 if do not clone system volume, don't add system volume to bdms
            if not sys_clone and bool_index in [0, '0']:
                continue
            #3.2 get volume id
            volume['id'] = resources.get(vol_res_name).get('id')
            volume_ext_properties = resources.get(vol_res_name).get('extra_properties')
            if volume_ext_properties:
                volume['guest_format'] = volume_ext_properties.get('guest_format')
                volume['mount_point'] = volume_ext_properties.get('mount_point')
            bdms.append(volume)
            
            
        #4. create transform data port to new instances
        server_az = server._info.get('OS-EXT-AZ:availability_zone')
        
        if not server_az:
            LOG.error('Can not get the availability_zone of server %s', server.id)
            raise exception.AvailabilityZoneNotFound(server_uuid=server.id)
        
        migrate_net_map = CONF.migrate_net_map
        migrate_net_id = migrate_net_map.get(server_az)
        if not migrate_net_id:
            LOG.error('Can not get the migrate net of server %s', server.id)
            raise exception.NoMigrateNetProvided(server_uuid=server.id)
        
        #4.1 call neutron api create port
        LOG.debug("Instance template driver attach port to instance start")
        net_info = self.nova_api.interface_attach(context, server.id, migrate_net_id,
                                                  port_id=None, fixed_ip=None)
        
        interface_attachment = net_info._info
        if interface_attachment:
            LOG.debug('The interface attachment info is %s ' %str(interface_attachment))
            des_gw_ip = interface_attachment.get('fixed_ips')[0].get('ip_address')
            port_id = interface_attachment.get('port_id')
        else:
            LOG.error("Instance template driver attach port failed")
            raise exception.NoMigrateNetProvided(server_uuid=server.id)

        #waiting port attach finished, and can ping this vm
        if port_wait_fun:
            port_wait_fun(context, port_id)
            
        LOG.debug("Instance template driver attach port end: %s", des_gw_ip)
        #des_gw_url = ip:port
        des_port = str(CONF.v2vgateway_api_listen_port)
        des_gw_url = des_gw_ip + ":" + des_port
        
        src_gw_url = ext_properties.get('gw_url')
        
        src_urls = src_gw_url.split(':')
        
        if len(src_urls) != 2:
            LOG.error("Input source gw url error: %s", src_gw_url)
            msg = "Input source gw url error: " + src_gw_url
            raise exception.InvalidInput(reason=msg)
        
        #5. request birdiegateway service to clone each volume data
        for bdm in bdms:
            # 6.1 TODO: query cloned new VM volume name
            src_dev_name = bdm.get('device_name')
            des_dev_name = src_dev_name
            src_dev_format = bdm.get('guest_format')
            # if template does not hava disk format and mount point info
            # query them from conveyor-agent
            if not src_dev_format:
                client = birdiegatewayclient.get_birdiegateway_client(src_urls[0], src_urls[1])
                src_dev_format = client.vservices.get_disk_format(src_dev_name).get('disk_format')
                
            src_mount_point = bdm.get('mount_point')
            
            if not src_mount_point:
                client = birdiegatewayclient.get_birdiegateway_client(src_urls[0], src_urls[1])
                src_mount_point = client.vservices.get_disk_mount_point(src_dev_name).get('mount_point')
                
            mount_point = []
            mount_point.append(src_mount_point)   
            LOG.debug("Volume %(dev_name)s disk format is %(disk_format)s and mount point is %(point)s",
                      {'dev_name': src_dev_name, 'disk_format': src_dev_format, 'point': src_mount_point})          
           
            # get conveyor gateway client to call birdiegateway api
            LOG.debug("Instance template driver transform data start")
            client = birdiegatewayclient.get_birdiegateway_client(des_gw_ip, des_port)
            client.vservices.clone_volume(src_dev_name,
                                          des_dev_name,
                                          src_dev_format,
                                          mount_point,
                                          src_gw_url,
                                          des_gw_url)
        LOG.debug("Instance template driver transform data end")
        
        #7. TODO: check data is transforming finished
        if trans_data_wait_fun:
            trans_data_wait_fun(context)
            
        #8 TODO: deatach data port for new intsance
        self.nova_api.interface_detach(context, server.id, port_id)
        
        
        LOG.debug("Clone instances end in template driver")
        


        
