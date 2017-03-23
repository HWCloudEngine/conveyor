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

    def network_list(self, context, **_params):
        networks = []
        try:
            networks = self.call('list_network')
        except Exception as e:
            LOG.error(_LE('Query networks info error: %s'), e)
            raise exception.V2vException
        return networks

    def get_network(self, context, network_id, timeout=None, **_params):
        network = None
        try:
            network = self.call('get_subnet')
        except Exception as e:
            LOG.error(_LE('Query network %(id)s info error: %(err)s'),
                      {'id': network_id, 'err': e})
            raise exception.ResourceNotFound(resource_type='Network',
                                             resource_id=network_id)
        return network

    def subnet_list(self, context, **_params):
        subnets = []
        try:
            subnets = self.call('list_subnet')
        except Exception as e:
            LOG.error(_LE('Query subnets info error: %s'), e)
            raise exception.V2vException
        return subnets

    def get_subnet(self, context, subnet_id, **_params):
        subnet = None
        try:
            subnet = self.call('get_subnet')
        except Exception as e:
            LOG.error(_LE('Query subnet %(id)s info error: %(err)s'),
                      {'id': subnet_id, 'err': e})
            raise exception.ResourceNotFound(resource_type='Network',
                                             resource_id=subnet_id)
        return subnet

    def secgroup_list(self, context, **_params):
        security_groups = []
        try:
            security_groups = self.call('list_security_group')
        except Exception as e:
            LOG.error(_LE('Query security groups info error: %s'), e)
            raise exception.V2vException
        return security_groups

    def get_security_group(self, context, security_group_id, **_params):
        security_group = None
        try:
            security_group = self.call('get_security_group')
        except Exception as e:
            LOG.error(_LE('Query security group %(id)s info error: %(err)s'),
                      {'id': security_group_id, 'err': e})
            raise exception.ResourceNotFound(resource_type='Network',
                                             resource_id=security_group_id)
        return security_group

    def floatingip_list(self, context, **_params):
        pass

    def get_floatingip(self, context, floatingip_id, **_params):
        pass

    def router_list(self, context, **_params):
        pass

    def get_router(self, context, router_id, **_params):
        pass

    def router_interfaces_list(self, context, router_id):
        pass

    def port_list(self, context, **_params):

        ports = []
        try:
            ports = self.call('list_port')
        except Exception as e:
            LOG.error(_LE('Query ports info error: %s'), e)
            raise exception.V2vException
        return ports

    def get_port(self, context, port_id, **_params):

        port = None
        try:
            port = self.call('get_port')
        except Exception as e:
            LOG.error(_LE('Query port %(id)s info error: %(err)s'),
                      {'id': port_id, 'err': e})
            raise exception.ResourceNotFound(resource_type='Network',
                                             resource_id=port_id)
        return port

    def vip_list(self, context, **_params):
        pass

    def get_vip(self, context, vip_id, **_params):
        pass

    def create_port(self, context, _params):
        pass

    def delete_port(self, context, port_id):
        pass

    def allocate_floating_ip(self, context, pool=None):
        pass

    def disassociate_floating_ip(self, context, floatingip_id,
                                 affect_auto_assigned=False):
        pass

    def associate_floating_ip(self, context,
                              floatingip_id, port_id,
                              fixed_address=None,
                              affect_auto_assigned=False):
        pass

    def list_pools(self, context, **_params):
        pass

    def show_pool(self, context, pool, **_params):
        pass

    def list_members(self, context, **_params):
        pass

    def show_member(self, context, member, **_params):
        pass

    def list_health_monitors(self, context, **_params):
        pass

    def show_health_monitor(self, context, health_monitor, **_params):
        pass

    def list_listeners(self, context, vip_id, retrieve_all=True, **_params):
        pass

    def show_listener(self, context, listener_id, vip_id, **_params):
        pass
