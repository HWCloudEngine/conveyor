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
Handles all requests relating to volumes + cinder.
"""

from neutronclient.common import exceptions
from neutronclient.v2_0 import client as neutron_client

from oslo.config import cfg

from conveyor.common import log as logging

from conveyor import exception
from conveyor.i18n import _
from conveyor.i18n import _LW

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
        return neutronclient(context).show_network(network_id, **_params)['network']
            
    def subnet_list(self, context, **_params):
        return neutronclient(context).list_subnets(**_params)['subnets']
    
    def get_subnet(self, context, subnet_id, **_params):
        return neutronclient(context).show_subnet(subnet_id, **_params)['subnet']
    
    def secgroup_list(self, context, **_params):
        return neutronclient(context).list_security_groups(**_params)['security_groups']
    
    def get_security_group(self, context, security_group_id, **_params):
        return neutronclient(context).show_security_group(security_group_id, **_params)['security_group']

    def floatingip_list(self, context, **_params):
        return neutronclient(context).list_floatingips(**_params)['floatingips']
            
    def get_floatingip(self, context, floatingip_id, **_params):
        return neutronclient(context).show_floatingip(floatingip_id, **_params)['floatingip']
            
    def router_list(self, context, **_params):
        return neutronclient(context).list_routers(**_params)['routers']

    def get_router(self, context, router_id, **_params):
        return neutronclient(context).show_router(router_id, **_params)['router']

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

