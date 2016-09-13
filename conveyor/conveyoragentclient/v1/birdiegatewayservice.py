# Copyright 2011 Denali Systems, Inc.
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

"""
Volume interface (1.1 extension).
"""

try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode
import six

from conveyor.common import log as logging
from conveyor.common import uuidutils
from conveyor.conveyoragentclient.common import base

LOG = logging.getLogger(__name__)


class VServiceManager(base.Manager):
    """
    Manage :class:`VService` resources.
    """
    
    def __init__(self, client=None, url=None):
        
        super(VServiceManager, self).__init__(client, url)

    def create(self):
        pass

    def get(self, id):
        pass
        
    def delete(self):
        pass

    def update(self, volume, **kwargs):
        pass
        
        
    def clone_volume(self, src_dev_name, des_dev_name, src_dev_format,
                     src_mount_point, src_gw_url, des_gw_url,
                     trans_protocol=None, trans_port=None):
        
        '''Clone volume data'''
        
        LOG.debug("Clone volume data start")
        
        body = {'clone_volume': {'src_dev_name': src_dev_name,
                           'des_dev_name': des_dev_name,
                           'src_dev_format': src_dev_format,
                           'src_mount_point': src_mount_point,
                           'src_gw_url': src_gw_url,
                           'des_gw_url': des_gw_url,
                           'trans_protocol': trans_protocol,
                           'trans_port': trans_port
                           }}
        
        
        rsp = self._clone_volume("/v2vGateWayServices", body)
        LOG.debug("Clone volume %(dev)s data end: %(rsp)s",
                  {'dev': src_dev_name, 'rsp': rsp})
        return rsp
        
    def mount_disk(self, dev_name, mount_point):
        
        '''Mount disk'''
        
        LOG.debug("Mount disk: %(dev_name)s to %(mount_point)s start", 
                  {'disk_name': dev_name, 'mount_point': mount_point})
        
        body = {'mountDisk': {'disk': {'disk_name': dev_name},
                               'mount_point': mount_point}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        return self._mount_disk(url, body)
    
    def get_disk_format(self, dev_name):
        LOG.debug("Query disk: %s format start", dev_name)
        body = {'getDiskFormat': {'disk_name': dev_name}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        
        disk_format = self._get_disk_format(url, body)
        
        LOG.debug("Query disk: %(dev_name)s to %(mount_point)s start", 
                  {'dev_name': dev_name, 'mount_point': disk_format})
        
        return disk_format
    
    def get_disk_mount_point(self, dev_name):
        
        LOG.debug("Query disk: %s mount point start", dev_name)
        body = {'getDiskMountPoint': {'disk_name': dev_name}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        
        mount_point = self._get_disk_mount_point(url, body)
        
        LOG.debug("Query disk: %(dev_name)s mount pint: %(mount_point)s end", 
                  {'dev_name': dev_name, 'mount_point': mount_point})
        
        return mount_point

    def get_disk_name(self, volume_id):
        
        LOG.debug("Query disk: %s name start", volume_id)
        body = {'getDiskName': {'volume_id': volume_id}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        
        dev_name = self._get_disk_name(url, body)
        
        LOG.debug("Query disk: %(dev_name)s name: %(mount_point)s end", 
                  {'dev_name': volume_id, 'mount_point': dev_name})
        
        return dev_name
    
    def get_data_trans_status(self, task_id):
        
        LOG.debug("Query data transformer state start")
        
        url = '/v2vGateWayServices/%s' % task_id
        
        rsp =  self._get(url)
        
        LOG.debug("Query data transformer state end: %s", rsp)
        
        return rsp
    
    def force_mount_disk(self, dev_name, mount_point):
        
        '''Mount disk'''
        
        LOG.debug("Force mount disk: %(dev_name)s to %(mount_point)s start", 
                  {'dev_name': dev_name, 'mount_point': mount_point})
        
        body = {'forceMountDisk': {'disk': {'disk_name': dev_name},
                               'mount_point': mount_point}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        return self._mount_disk(url, body)
    
    def _force_umount_disk(self, mount_point):

        '''uMount disk'''
        
        LOG.debug("Force umount %(mount_point)s start", 
                  {'mount_point': mount_point})
        
        body = {'forceUmountDisk': {'mount_point': mount_point}}
        
        url = '/v2vGateWayServices/%s/action' % uuidutils.generate_uuid()
        return self._post(url, body)









 







