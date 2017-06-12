# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Handles all requests relating to neutron.
"""

from neutronclient.v2_0 import client as neutron_client
from oslo_config import cfg
from oslo_log import log as logging

neutron_opts = [
    cfg.StrOpt('url',
               default='http://127.0.0.1:9696',
               help='URL for connecting to neutron',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_url'),
    cfg.IntOpt('url_timeout',
               default=30,
               help='Timeout value for connecting to neutron in seconds',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_url_timeout'),
    cfg.StrOpt('admin_username',
               help='Username for connecting to neutron in admin context',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_admin_username'),
    cfg.StrOpt('admin_password',
               help='Password for connecting to neutron in admin context',
               secret=True,
               deprecated_group='DEFAULT',
               deprecated_name='neutron_admin_password'),
    cfg.StrOpt('admin_auth_url',
               default='http://localhost:5000/v2.0',
               help='Authorization URL for connecting to neutron in admin '
               'context',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_admin_auth_url'),
    cfg.BoolOpt('api_insecure',
                default=False,
                help='If set, ignore any SSL validation issues',
                deprecated_group='DEFAULT',
                deprecated_name='neutron_api_insecure'),
    cfg.StrOpt('auth_strategy',
               default='keystone',
               help='Authorization strategy for connecting to '
                    'neutron in admin context',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_auth_strategy'),
    cfg.StrOpt('ca_certificates_file',
               help='Location of CA certificates file to use for '
                    'neutron client requests.',
               deprecated_group='DEFAULT',
               deprecated_name='neutron_ca_certificates_file'),
   ]

CONF = cfg.CONF
CONF.register_opts(neutron_opts, 'neutron')
LOG = logging.getLogger(__name__)


def neutronclient(context):

    params = {
        'username': CONF.neutron.admin_username,
        'password': CONF.neutron.admin_password,
        'auth_url': CONF.neutron.admin_auth_url,
        'endpoint_url': CONF.neutron.url,
        'timeout': CONF.neutron.url_timeout,
        'insecure': CONF.neutron.api_insecure,
        'ca_cert': CONF.neutron.ca_certificates_file,
        'auth_strategy': CONF.neutron.auth_strategy,
        'token': context.auth_token,
        'tenant_id': context.project_id
    }

    return neutron_client.Client(**params)


class API(object):
    """API for interacting with the neutron manager."""

    def network_list(self, context, **_params):
        return neutronclient(context).list_networks(**_params)['networks']

    def get_network(self, context, network_id, timeout=None, **_params):
        return neutronclient(context).show_network(network_id,
                                                   **_params)['network']

    def subnet_list(self, context, **_params):
        return neutronclient(context).list_subnets(**_params)['subnets']

    def get_subnet(self, context, subnet_id, **_params):
        return neutronclient(context).show_subnet(subnet_id,
                                                  **_params)['subnet']

    def secgroup_list(self, context, **_params):
        return neutronclient(context).\
            list_security_groups(**_params)['security_groups']

    def get_security_group(self, context, security_group_id, **_params):
        security_group = neutronclient(context).\
            show_security_group(security_group_id,
                                **_params)['security_group']
        rules = security_group.get('security_group_rules', [])
        for rule in rules:
            rule.pop('description', None)
        return security_group

    def floatingip_list(self, context, **_params):
        return neutronclient(context).\
            list_floatingips(**_params)['floatingips']

    def get_floatingip(self, context, floatingip_id, **_params):
        return neutronclient(context).show_floatingip(floatingip_id,
                                                      **_params)['floatingip']

    def router_list(self, context, **_params):
        return neutronclient(context).list_routers(**_params)['routers']

    def get_router(self, context, router_id, **_params):
        return neutronclient(context).show_router(router_id,
                                                  **_params)['router']

    def router_interfaces_list(self, context, router_id):
        return neutronclient(context).list_ports(device_id=router_id)['ports']

    def port_list(self, context, **_params):
        return neutronclient(context).list_ports(**_params)['ports']

    def get_port(self, context, port_id, **_params):
        return neutronclient(context).show_port(port_id, **_params)['port']

    def vip_list(self, context, **_params):
        return neutronclient(context).list_vips(**_params)['vips']

    def get_vip(self, context, vip_id, **_params):
        return neutronclient(context).show_vip(vip_id, **_params)['vip']

    def create_port(self, context, _params):
        return neutronclient(context).create_port(_params)['port']['id']

    def delete_port(self, context, port_id):
        return neutronclient(context).delete_port(port_id)

    def allocate_floating_ip(self, context, pool=None):
        param = {'floatingip': {'floating_network_id': pool}}
        fip = neutronclient(context).create_floatingip(param)
        return fip['floatingip']['floating_ip_address']

    def disassociate_floating_ip(self, context, floatingip_id,
                                 affect_auto_assigned=False):
        """Disassociate a floating ip from the instance."""
        neutronclient(context).update_floatingip(floatingip_id,
                                                 {'floatingip': {'port_id':
                                                                     None}})

    def associate_floating_ip(self, context,
                              floatingip_id, port_id, fixed_address=None,
                              affect_auto_assigned=False):
        """Associate a floating ip with a fixed ip."""
        param = {'port_id': port_id}
        if fixed_address:
            param['fixed_ip_address'] = fixed_address
        neutronclient(context).update_floatingip(floatingip_id,
                                                 {'floatingip': param})

    def list_pools(self, context, **_params):
        return neutronclient(context).list_pools(**_params)

    def show_pool(self, context, pool, **_params):

        return neutronclient(context).show_pool(pool, **_params)

    def list_members(self, context, **_params):

        return neutronclient(context).list_members(**_params)

    def show_member(self, context, member, **_params):

        return neutronclient(context).show_member(member, **_params)

    def list_health_monitors(self, context, **_params):

        return neutronclient(context).list_health_monitors(**_params)

    def show_health_monitor(self, context, health_monitor, **_params):

        return neutronclient(context).show_health_monitor(health_monitor,
                                                          **_params)

    def list_listeners(self, context, vip_id, retrieve_all=True, **_params):
        return neutronclient(context).list_vip_listener(vip_id,
                                                        retrieve_all=
                                                        retrieve_all,
                                                        **_params)

    def show_listener(self, context, listener_id, vip_id, **_params):
        return neutronclient(context).show_vip_listener(vip_id,
                                                        listener_id,
                                                        **_params)
