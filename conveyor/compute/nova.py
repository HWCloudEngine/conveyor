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
Handles all requests to Nova.
"""


from novaclient import service_catalog
from novaclient.v1_1 import client as nova_client
from novaclient.v1_1.contrib import assisted_volume_snapshots
from oslo.config import cfg

from conveyor.common import log as logging

nova_opts = [
    cfg.StrOpt('nova_catalog_info',
               default='compute:nova:publicURL',
               help='Match this value when searching for nova in the '
                    'service catalog. Format is: separated values of '
                    'the form: '
                    '<service_type>:<service_name>:<endpoint_type>'),
    cfg.StrOpt('nova_catalog_admin_info',
               default='compute:nova:adminURL',
               help='Same as nova_catalog_info, but for admin endpoint.'),
    cfg.StrOpt('nova_endpoint_template',
               default=None,
               help='Override service catalog lookup with template for nova '
                    'endpoint e.g. http://localhost:8774/v2/%(project_id)s'),
    cfg.StrOpt('nova_endpoint_admin_template',
               default=None,
               help='Same as nova_endpoint_template, but for admin endpoint.'),
    cfg.StrOpt('os_region_name',
               default='cloud.hybrid',
               help='Region name of this node'),
    cfg.StrOpt('nova_ca_certificates_file',
               default=None,
               help='Location of ca certificates file to use for nova client '
                    'requests.'),
    cfg.BoolOpt('nova_api_insecure',
                default=True,
                help='Allow to perform insecure SSL requests to nova'),
]

CONF = cfg.CONF
CONF.register_opts(nova_opts)

CONF.import_opt('auth_protocol', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_host', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_port', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_version', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_tenant_name', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_user', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_password', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')

LOG = logging.getLogger(__name__)


def novaclient(context, admin=False):
    # FIXME: the novaclient ServiceCatalog object is mis-named.
    #        It actually contains the entire access blob.
    # Only needed parts of the service catalog are passed in, see
    # nova/context.py.
    compat_catalog = {
        'access': {'serviceCatalog': context.service_catalog or []}
    }
    sc = service_catalog.ServiceCatalog(compat_catalog)

    nova_endpoint_template = CONF.nova_endpoint_template
    nova_catalog_info = CONF.nova_catalog_info

    if admin:
        nova_endpoint_template = CONF.nova_endpoint_admin_template
        nova_catalog_info = CONF.nova_catalog_admin_info

    if nova_endpoint_template:
        url = nova_endpoint_template % context.to_dict()
    else:
        info = nova_catalog_info
        service_type, service_name, endpoint_type = info.split(':')
        # extract the region if set in configuration
        if CONF.os_region_name:
            attr = 'region'
            filter_value = CONF.os_region_name
        else:
            attr = None
            filter_value = None
        try:
            url = sc.url_for(attr=attr,
                         filter_value=filter_value,
                         service_type=service_type,
                         service_name=service_name,
                         endpoint_type=endpoint_type)
        except Exception as e:
            LOG.error("Novaclient get URL from service_catalog error: %s" % e)
            return adminclient(context) 

    LOG.debug('Novaclient connection created using URL: %s' % url)
    LOG.debug("Novaclient connection select URL from: %s" % context.service_catalog)
    if not url:
        return adminclient(context)
    
    extensions = [assisted_volume_snapshots]

    c = nova_client.Client(context.user_id,
                           context.auth_token,
                           context.project_id,
                           auth_url=url,
                           insecure=CONF.nova_api_insecure,
                           cacert=CONF.nova_ca_certificates_file,
                           extensions=extensions)
    # noauth extracts user_id:project_id from auth_token
    c.client.auth_token = context.auth_token or '%s:%s' % (context.user_id,
                                                           context.project_id)
    c.client.management_url = url
    return c



def adminclient(context):

    auth_url = "%s://%s:%s/identity/%s" % (
                        CONF.keystone_authtoken.auth_protocol,
                        CONF.keystone_authtoken.auth_host,
                        CONF.keystone_authtoken.auth_port,
                        CONF.keystone_authtoken.auth_version)
    
    c = nova_client.Client(CONF.keystone_authtoken.admin_user,
                           CONF.keystone_authtoken.admin_password,
                           CONF.keystone_authtoken.admin_tenant_name,
                           auth_url=auth_url,
                           insecure=CONF.nova_api_insecure,
                           cacert=CONF.nova_ca_certificates_file,
                           region_name=CONF.os_region_name)

    return c


class API(object):
    """API for interacting with novaclient."""
    
    def get_server(self, context, server_id):
        
        client = novaclient(context, admin=True)
        LOG.debug("Nova client query server %s start", server_id)
        server = client.servers.get(server_id)
        LOG.debug("Nova client query server %s end", str(server))
        return server
    
    def delete_server(self, context, server_id):
        client = novaclient(context, admin=True)
        LOG.debug("Nova client delete server %s start", server_id)
        server = client.servers.delete(server_id)
        LOG.debug("Nova client delete server %s end", str(server))
        

    def get_all_servers(self, context, detailed=True, search_opts=None, 
                                                marker=None, limit=None):
        LOG.debug("Nova client query all servers start")
        
        client = novaclient(context, admin=True)
        return client.servers.list(detailed=detailed, 
                                   search_opts=search_opts,
                                   marker=marker, limit=limit)
        LOG.debug("Nova client query all servers end")
   
    def create_instance(self, context, name, image, flavor, meta=None, files=None,
               reservation_id=None, min_count=None,
               max_count=None, security_groups=None, userdata=None,
               key_name=None, availability_zone=None,
               block_device_mapping=None, block_device_mapping_v2=None,
               nics=None, scheduler_hints=None, config_drive=None, 
               disk_config=None, **kwargs):
        
        nova = novaclient(context, admin=True)
        
        return nova.servers.create(name, image,
                                flavor, meta=meta, files=files,
                                reservation_id=reservation_id,
                                min_count=min_count, max_count=max_count,
                                security_groups=security_groups,
                                userdata=userdata,
                                key_name=key_name,
                                availability_zone=availability_zone,
                                block_device_mapping=block_device_mapping,
                                block_device_mapping_v2=block_device_mapping_v2,
                                nics=nics, scheduler_hints=scheduler_hints,
                                config_drive=config_drive, disk_config=disk_config,
                                **kwargs)
    
    
    def attach_volume(self, context, server_id, volume_id, device):
        """
        Attach a volume identified by the volume ID to the given server ID

        :param server_id: The ID of the server
        :param volume_id: The ID of the volume to attach.
        :param device: The device name
        :rtype: :class:`Volume`
        """
        
        nova = novaclient(context, admin=True)
              
        return nova.volumes.create_server_volume(server_id, volume_id,
                                                device)

    
    def detach_volume(self,  context, server_id, attachment_id):

        """
        Detach a volume identified by the attachment ID from the given server

        :param server_id: The ID of the server
        :param attachment_id: The ID of the attachment
        """
        nova = novaclient(context, admin=True)
        return nova.volumes.delete_server_volume(server_id, attachment_id)
    
    def interface_attach(self, context, server_id, net_id, port_id=None, fixed_ip=None):
        LOG.debug("Nova client attach a interface to %s start",server_id)
     
        LOG.debug("Nova client query server %s start", server_id)
        client = novaclient(context, admin=True)
        server = client.servers.get(server_id)
        LOG.debug("Nova client query server %s end", str(server))
        obj = client.servers.interface_attach(server, port_id, net_id, fixed_ip)
        return obj
    
    def interface_detach(self, context, server_id, port_id):
        LOG.debug("Nova client detach a interface from %s start",server_id)
     
        LOG.debug("Nova client query server %s start", server_id)
        client = novaclient(context, admin=True)
        server = client.servers.get(server_id)
        LOG.debug("Nova client query server %s end", str(server))
        return client.servers.interface_detach(server, port_id)
        
    def associate_floatingip(self, context, server_id, address, fixed_address=None):
        LOG.debug("Nova client associate a floatingip %s to server %s start", address, server_id)
        client = novaclient(context, admin=True)
        client.servers.add_floating_ip(server_id, address, fixed_address)    
        
       
    def migrate_interface_detach(self, context, server_id, port_id):
        client = adminclient(context)
        return client.servers.interface_detach(server_id, port_id)
            
    def keypair_list(self, context): 
        return novaclient(context, admin=True).keypairs.list()
            
    def get_keypair(self, context, keypair_id): 
        return novaclient(context, admin=True).keypairs.get(keypair_id)

    def flavor_list(self, context, detailed=True, is_public=True): 
        return novaclient(context, admin=True).flavors.list(detailed=detailed,
                                                            is_public=is_public)
            
    def get_flavor(self, context, flavor_id): 
        return novaclient(context, admin=True).flavors.get(flavor_id)

    def server_security_group_list(self, context, server):
        return novaclient(context, admin=True).servers.list_security_group(server)

    
    def availability_zone_list(self, context, detailed=True):
        return novaclient(context, admin=True).availability_zones.list(detailed=detailed)
    
        