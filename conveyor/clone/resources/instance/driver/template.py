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
from conveyor.i18n import _, _LE, _LI, _LW
from conveyor import volume 
from conveyor import compute
from conveyor import image as glance_image
from conveyor import exception
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
import time

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


class TemplateCloneDriver(object):
    """Manages the running instances from creation to destruction."""

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        self.cinder_api = volume.API()
        self.nova_api = compute.API()
        self.image_api = glance_image.API()
        
    def start_template_clone(self, context, instance, create_volume_wait_fun=None,
                             volume_wait_fun=None,
                             trans_data_wait_fun=None,
                             create_instance_wait_fun=None,
                             port_wait_fun=None):
        LOG.debug("Clone instances starting in template driver")
        
        #1.check if clone system volume
        if instance['sys_clone']:
            self._start_template_clone_with_sys(context, instance,
                                                create_volume_wait_fun=trans_data_wait_fun,
                                                volume_wait_fun=volume_wait_fun,
                                                trans_data_wait_fun=trans_data_wait_fun,
                                                create_instance_wait_fun=create_instance_wait_fun)
            return
        
        #2. check volumes paramenters; if having volume is attached after instances running
        #here create this volume firstly
        bdms = instance['block_device_mapping_v2']
        
        #check bdm list having boot volume or not
        boot_volume = False
        block_device_mapping_v2 = []
        for bdm in bdms:
            volume_type = bdm.get('volume_type') or None
            
            if volume_type:
                size = bdm['volume_size']
                name = bdm['device_name']
                volume = self.cinder_api.create_volume(context, size,
                                                       name,
                                                       volume_type=volume_type)
                
                #2.1 waiting volume create finished
                if create_volume_wait_fun:
                    create_volume_wait_fun(context, volume['id'])
                
                #add create volume id to block_device_map_v2   
                bdm['volume_id'] = volume['id']
                
            boot = bdm.get('boot_index') or -1
            LOG.debug("Volume boot is %s", boot)
            if 0 == boot or '0' == boot:
                LOG.debug("Volume booting")
                boot_volume = True
            
            _new_bdm = dict(bdm)
            for f in ['mount_point', 'guest_format', 'os_device']:
                if f in _new_bdm:
                    _new_bdm.pop(f)
            
            block_device_mapping_v2.append(_new_bdm)
            
        #3. getting create instances parameters
        name = instance['name']
        image = instance['image']
        flavor = instance['flavor']
       
        #4. create instance
        #4.1 if BDM d not have boot volume, here must query image class
        image_cls=None
        
        if boot_volume == False:
            LOG.debug("Instance template driver query image start")
            image_dict = self.image_api.get(context, image)
            image_cls = glance_image.glance.Image(image_dict['id'],
                                           image_dict['name'],
                                           image_dict['size'])
            LOG.debug("Instance template driver query image: %s", str(image_dict))
            
        flavor = self.nova_api.get_flavor(context, flavor)
        LOG.debug("Instance template driver query flavor: %s", str(flavor))
        #get all instance info
        
        meta = instance.get('meta') or None
        files = instance.get('files') or None
        userdata= instance.get('userdata') or None
        reservation_id = instance.get('reservation_id') or None
        min_count = instance.get('min_count') or None
        max_count = instance.get('max_count') or None
        security_groups = instance.get('security_groups') or None
        key_name = instance.get('key_name') or None
        availability_zone = instance.get('availability_zone') or None
        scheduler_hints = instance.get('scheduler_hints') or None
        config_drive = instance.get('config_drive') or None
        disk_config = instance.get('disk_config') or None
        nics = instance.get('networks') or None
        
        boot_kwargs = dict(
            meta=meta, files=files, userdata=userdata,
            reservation_id=reservation_id, min_count=min_count,
            max_count=max_count, security_groups=security_groups,
            key_name=key_name, availability_zone=availability_zone,
            nics=nics, block_device_mapping_v2=block_device_mapping_v2,
            scheduler_hints=scheduler_hints, config_drive=config_drive,
            disk_config=disk_config)
        
        #create instance
        LOG.debug("Instance template driver create instance start")     
        server = self.nova_api.create_instance(context, name, image_cls, flavor, **boot_kwargs)
        LOG.debug("Instance template driver create instance end: %s", str(server)) 
        
        #waiting instance create finished
        if create_instance_wait_fun:
            create_instance_wait_fun(context, server.id)
            
        #5. create transform data port to new instances
        server_az = server._info.get('OS-EXT-AZ:availability_zone')
        
        if not server_az:
            LOG.error('Can not get the availability_zone of server %s', server.id)
            raise exception.AvailabilityZoneNotFound(server_uuid=server.id)
        
        migrate_net_map = CONF.migrate_net_map
        migrate_net_id = migrate_net_map.get(server_az)
        if not migrate_net_id:
            LOG.error('Can not get the migrate net of server %s', server.id)
            raise exception.NoMigrateNetProvided(server_uuid=server.id)
        
        #5.1 call neutron api create port
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
        
        src_gw_url = instance['gw_url']
        
        
        #6. request birdiegateway service to clone each volume data
        for bdm in bdms:
            if bdm.get('boot_index') == 0 or  bdm.get('boot_index')=='0':
                continue
            #6.1 TODO: query cloned new VM volume name
            src_dev_name = bdm.get('os_device')
            des_dev_name = src_dev_name
            src_dev_format = bdm['guest_format']
            src_mount_point = bdm['mount_point']
           
            # get conveyor gateway client to call birdiegateway api
            LOG.debug("Instance template driver transform data start")
            client = birdiegatewayclient.get_birdiegateway_client(des_gw_ip, des_port)
            client.vservices.clone_volume(src_dev_name,
                                          des_dev_name, 
                                          src_dev_format,
                                          src_mount_point, 
                                          src_gw_url, 
                                          des_gw_url)
            LOG.debug("Instance template driver transform data end")
        
        #7. TODO: check data is transforming finished
        if trans_data_wait_fun:
            trans_data_wait_fun(context)
            
        #8 TODO: deatach data port for new intsance
        self.nova_api.interface_detach(context, server.id, port_id)
        
        
        LOG.debug("Clone instances end in template driver")
        
    
    def _start_template_clone_with_sys(self, context, instance, create_volume_wait_fun=None,
                             volume_wait_fun=None, trans_data_wait_fun=None,
                             create_instance_wait_fun=None, port_wait_fun=None):
        
        LOG.debug("Clone instance with system volume starting in template driver")
        
        #1. create all volumes
        bdms = instance['block_device_mapping_v2']
        
        #get v2v VM id
        v2v_vm_id = CONF.data_trans_vm
        vm_host = CONF.data_trans_vm_host
        vm_port = str(CONF.data_trans_vm_port)
        des_gw_url = vm_host + ":" + vm_port
        src_gw_url = instance['gw_url']
        
        block_device_mapping_v2 = []
        #create volumes and attach them to gw VM
        for bdm in bdms:
            volume_type = bdm.get("volume_type") or None
            size = bdm['volume_size']
            name = bdm.get("device_name") or None
            #2.1 create volume
            LOG.debug("Instance template driver create volume start: %s", name)
            volume = self.cinder_api.create_volume(context, size, name,
                                                volume_type=volume_type)           
            LOG.debug("Instance template driver create volume end: %s", str(volume))
            
            #waiting volume create finished           
            if create_volume_wait_fun:
                create_volume_wait_fun(context, volume['id'])
                       
            #2.2 attach volume to v2v VM
            volume_id = volume['id']
            device = bdm['os_device']
        
            LOG.debug("Instance template driver attach volume start: %s", device)
            self.nova_api.attach_volume(context, v2v_vm_id, volume_id, device)
            LOG.debug("Instance template driver attach volume end")
            
            if volume_wait_fun:
                volume_wait_fun(context, volume['id'], 'in-use')
            
            src_dev_name = bdm['os_device']
            des_dev_name = src_dev_name
            src_dev_format = bdm['guest_format']
            src_mount_point = bdm['mount_point']
        
            #2.3 request birdiegateway service to clone each volume data
            LOG.debug("Instance template driver transform volume start")
            client = birdiegatewayclient.get_birdiegateway_client(vm_host, vm_port)
            client.vservices.clone_volume(src_dev_name,
                                          des_dev_name, 
                                          src_dev_format,
                                          src_mount_point, 
                                          src_gw_url, 
                                          des_gw_url)
            
            if trans_data_wait_fun:
                trans_data_wait_fun(context)
            
            LOG.debug("Instance template driver transform volume end")        
        
            #2.4 deatach volume to v2v VM
            LOG.debug("Instance template driver detach volume start: %s", volume_id)
            self.nova_api.detach_volume(context, v2v_vm_id, volume_id)                        
            #waiting volume detach finished            
            if volume_wait_fun:
                volume_wait_fun(context, volume['id'], 'available')
            
            LOG.debug("Instance template driver detach volume end: %s", volume_id)
            
            _new_bdm = dict(bdm)
            for f in ['mount_point', 'guest_format', 'os_device']:
                if f in _new_bdm:
                    _new_bdm.pop(f)
            
                       
            #2.5 add volume id to bdm
            bdm['volume_id'] = volume_id
            _new_bdm['volume_id'] = volume_id
            
            #2.6 if volume is system volume, deleting image id
            if _new_bdm['boot_index'] == 0 or _new_bdm['boot_index'] == '0':
                if _new_bdm.get('uuid'):
                    _new_bdm.pop('uuid')
            
            block_device_mapping_v2.append(_new_bdm)  
             
        #3. create intance with volumes
        name = instance['name']
        flavor = instance['flavor']
        flavor = self.nova_api.get_flavor(context, flavor)
        LOG.debug("Instance template driver query flavor: %s", str(flavor))
        #get all instance info
        block_device_mapping_v2 = block_device_mapping_v2
        meta = instance.get('meta') or None
        files = instance.get('files') or None
        userdata= instance.get('userdata') or None
        reservation_id = instance.get('reservation_id') or None
        min_count = instance.get('min_count') or None
        max_count = instance.get('max_count') or None
        security_groups = instance.get('security_groups') or None
        key_name = instance.get('key_name') or None
        availability_zone = instance.get('availability_zone') or None
        scheduler_hints = instance.get('scheduler_hints') or None
        config_drive = instance.get('config_drive') or None
        disk_config = instance.get('disk_config') or None
        nics = instance.get('networks') or None
        
        boot_kwargs = dict(
            meta=meta, files=files, userdata=userdata,
            reservation_id=reservation_id, min_count=min_count,
            max_count=max_count, security_groups=security_groups,
            key_name=key_name, availability_zone=availability_zone,
            nics=nics, block_device_mapping_v2=block_device_mapping_v2,
            scheduler_hints=scheduler_hints, config_drive=config_drive,
            disk_config=disk_config)
        
        LOG.debug("Instance template driver create vm start")
        self.nova_api.create_instance(context, name, None, flavor, **boot_kwargs)
        LOG.debug("Instance template driver create vm end")
        
        if create_instance_wait_fun:
            create_instance_wait_fun(context, instance['id'])   
                 
        #4. request birdiegateway service to mount volume to directory
        for bdm in bdms:
            dev_name = bdm['os_device']
            mount_point = bdm['mount_point']
            
            LOG.debug("Instance template mount disk start: %s", dev_name)
            client = birdiegatewayclient.get_birdiegateway_client(vm_host, vm_port)
            client.vservices.mount_disk(dev_name, mount_point)
            LOG.debug("Instance template mount disk end: %s", dev_name)
    
    
        LOG.debug("Clone instance with system volume end in template driver")
        
        

            
