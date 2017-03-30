# Copyright 2013 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Handles all requests to conveyorcaa.
"""

from oslo_config import cfg
from oslo_log import log as logging

from conveyor import exception

from conveyor.conveyorcaa.api import ConveyorcaaClientWrapper
from conveyor.i18n import _LE

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class API(ConveyorcaaClientWrapper):
    """API for interacting with novaclient."""

    def __init__(self, *args, **kwargs):
        super(ConveyorcaaClientWrapper, self).__init__(*args, **kwargs)

    def get_server(self, context, server_id):

        server = None

        try:
            server = self.call('get_server')
        except Exception as e:
            LOG.error(_LE('Query server %(id)s info error: %(err)s'),
                      {'id': server_id, 'err': e})
            raise exception.ResourceNotFound(resource_type='Nova',
                                             resource_id=server_id)
        return server

    def delete_server(self, context, server_id):
        pass

    def get_all_servers(self, context, detailed=True, search_opts=None,
                        marker=None, limit=None):
        servers = []
        try:
            servers = self.call('list_instances')
        except Exception as e:
            LOG.error(_LE('Query server list  info error: %s'), e)
        return servers

    def create_instance(self, context, name, image, flavor, meta=None,
                        files=None, reservation_id=None, min_count=None,
                        max_count=None, security_groups=None,
                        userdata=None, key_name=None, availability_zone=None,
                        block_device_mapping=None,
                        block_device_mapping_v2=None,
                        nics=None, scheduler_hints=None,
                        config_drive=None, disk_config=None,
                        **kwargs):
        pass

    def attach_volume(self, context, server_id, volume_id, device):
        try:
            self.call('attach_volume')
        except Exception as e:
            LOG.error(_LE('Attach volume %(vol_id)s to server %(vm)s: %(e)s'),
                      {'vol_id': volume_id, 'vm': server_id, 'e': e})
            raise exception.V2vException

    def detach_volume(self,  context, server_id, attachment_id):
        try:
            self.call('detach_volume')
        except Exception as e:
            LOG.error(_LE('Detach volume %(vol_id)s to server %(vm)s: %(e)s'),
                      {'vol_id': attachment_id, 'vm': server_id, 'e': e})
            raise exception.V2vException

    def interface_attach(self, context, server_id, net_id,
                         port_id=None, fixed_ip=None):
        pass

    def interface_detach(self, context, server_id, port_id):
        pass

    def associate_floatingip(self, context, server_id,
                             address, fixed_address=None):
        pass

    def migrate_interface_detach(self, context, server_id, port_id):
        pass

    def keypair_list(self, context):
        keypairs = []
        try:
            keypairs = self.call('list_keypair')
        except Exception as e:
            LOG.error(_LE('Query all keypairs info error: %s'), e)
            raise exception.V2vException
        return keypairs

    def get_keypair(self, context, keypair_id):
        keypair = None
        try:
            keypair = self.call('get_keypair')
        except Exception as e:
            LOG.error(_LE('Query keypair %(id)s info error: %(err)s'),
                      {'id': keypair_id, 'err': e})
            raise exception.V2vException
        return keypair

    def flavor_list(self, context, detailed=True, is_public=True):
        flavors = []
        try:
            flavors = self.call('list_flavor')
        except Exception as e:
            LOG.error(_LE('Query all flavors info error: %s'), e)
            raise exception.V2vException
        return flavors

    def get_flavor(self, context, flavor_id):
        flavor = None
        try:
            flavor = self.call('get_flavor')
        except Exception as e:
            LOG.error(_LE('Query flavor %(id)s info error: %(err)s'),
                      {'id': flavor_id, 'err': e})
            raise exception.V2vException
        return flavor

    def server_security_group_list(self, context, server):
        pass

    def availability_zone_list(self, context, detailed=True):
        availability_zones = []
        try:
            availability_zones = self.call('list_availability_zone')
        except Exception as e:
            LOG.error(_LE('Query all availability zone info error: %s'), e)
            raise exception.V2vException
        return availability_zones

    def reset_state(self, context, server_id, state):
        pass
