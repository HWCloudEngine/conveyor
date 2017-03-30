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
from novaclient.v2 import client as nova_client
from novaclient.v2.contrib import assisted_volume_snapshots

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.common import client as url_client
from conveyor.i18n import _LE

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
    cfg.StrOpt('nova_ca_certificates_file',
               default=None,
               help='Location of ca certificates file to use for nova client '
                    'requests.'),
    cfg.BoolOpt('nova_api_insecure',
                default=True,
                help='Allow to perform insecure SSL requests to nova'),

    cfg.StrOpt('nova_url',
               default="",
               help='Allow to perform insecure SSL requests to nova'),
]

CONF = cfg.CONF
CONF.register_opts(nova_opts)

CONF.import_opt('auth_protocol', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_host', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_port', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_version', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_tenant_name', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_user', 'keystonemiddleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('admin_password', 'keystonemiddleware.auth_token',
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
            LOG.error(_LE("Novaclient get URL from error: %s") % e)
            cs = url_client.Client()
            url = cs.get_service_endpoint(context, 'compute',
                                          region_name=CONF.os_region_name)
            LOG.debug(_LE("Novaclient get URL from common function: %s") % url)

    if not url:
        url = CONF.nova_url + '/' + context.project_id

    LOG.debug(_LE('Novaclient connection created using URL: %s') % url)

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

    def _object_to_dict(self, objs):
        res = []
        if not isinstance(objs, list):
            objs = [objs]
        for obj in objs:
            dt = obj.to_dict()
            if len(dt) == 1 and dt.keys()[0].lower() == 'nova':
                res.append(dt.values()[0])
            else:
                res.append(dt)
        return res

    def _dict_server(self, instance):

        instance_id = getattr(instance, 'id', '')
        instance_name = getattr(instance, 'name', '')
        availability_zone = \
            getattr(instance, 'OS-EXT-AZ:availability_zone', '')
        metadata = getattr(instance, 'metadata', {})
        user_data = getattr(instance, 'OS-EXT-SRV-ATTR:user_data', '')
        flavor = getattr(instance, 'flavor', {})
        keypair_name = getattr(instance, 'key_name', '')
        image = getattr(instance, 'image', '')
        volumes_attached = \
            getattr(instance, 'os-extended-volumes:volumes_attached', '')
        addresses = getattr(instance, 'addresses', {})
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state', None)
        power_state = getattr(instance, 'OS-EXT-STS:power_state', None)
        status = getattr(instance, 'status', None)

        server = {
                "id": instance_id,
                "name": instance_name,
                "OS-EXT-STS:vm_state": vm_state,
                "OS-EXT-STS:power_state": power_state,
                "metadata": metadata,
                "OS-EXT-SRV-ATTR:user_data": user_data,
                "image": image,
                "flavor": flavor,
                "addresses": addresses,
                "key_name": keypair_name,
                "os-extended-volumes:volumes_attached": volumes_attached,
                "OS-EXT-AZ:availability_zone": availability_zone,
                'status': status
        }

        return server

    def _dict_flavor(self, flavor):
        flavor_id = getattr(flavor, 'id', '')
        flavor_ram = getattr(flavor, 'ram', '')
        flavor_vcpus = getattr(flavor, 'vcpus', '')
        flavor_disk = getattr(flavor, 'disk', '')
        flavor_factor = getattr(flavor, 'rxtx_factor', '')
        flavor_public = getattr(flavor, 'os-flavor-access:is_public', '')
        flavor_ephemeral = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral', '')
        flavor_key = flavor.get_keys()
        flavor_swap = getattr(flavor, 'swap', '')

        flavor = {
                  "id": flavor_id,
                  "ram": flavor_ram,
                  "vcpus": flavor_vcpus,
                  "disk": flavor_disk,
                  "rxtx_factor": flavor_factor,
                  "os-flavor-access:is_public": flavor_public,
                  "OS-FLV-EXT-DATA:ephemeral": flavor_ephemeral,
                  "keys": flavor_key,
                  "swap": flavor_swap
                  }

        return flavor

    def _dict_keypair(self, keypair):
        key_id = getattr(keypair, 'id', '')
        key_name = getattr(keypair, 'name', '')
        public_key = getattr(keypair, 'public_key', '')
        keypair = {
                  "id": key_id,
                  "name": key_name,
                  "public_key": public_key
                   }
        return keypair

    def _dict_secgroup(self, secgroup):
        sec_id = getattr(secgroup, 'id', '')
        name = getattr(secgroup, 'name', '')
        sec = {
               'id': sec_id,
               'name': name
               }
        return sec

    def _dict_availability_zone(self, zones):
        return self._object_to_dict(zones)

    def get_server(self, context, server_id, is_dict=True):

        client = novaclient(context, admin=True)
        LOG.debug(_LE("Nova client query server %s start"), server_id)
        server = client.servers.get(server_id)
        if is_dict:
            server = self._dict_server(server)
        LOG.debug(_LE("Nova client query server %s end"), str(server))
        return server

    def delete_server(self, context, server_id):
        client = novaclient(context, admin=True)
        LOG.debug(_LE("Nova client delete server %s start"), server_id)
        server = client.servers.delete(server_id)
        LOG.debug(_LE("Nova client delete server %s end"), str(server))

    def get_all_servers(self, context, detailed=True, search_opts=None,
                        marker=None, limit=None, is_dict=True):
        LOG.debug(_LE("Nova client query all servers start"))
        client = novaclient(context, admin=True)
        server_list = client.servers.list(detailed=detailed,
                                          search_opts=search_opts,
                                          marker=marker, limit=limit)
        if server_list and is_dict:
            server_dict_list = []
            for server in server_list:
                server = self._dict_server(server)
                server_dict_list.append(server)
            return server_dict_list
        return server_list
        LOG.debug(_LE("Nova client query all servers end"))

    def create_instance(self, context, name, image, flavor,
                        meta=None, files=None,
                        reservation_id=None, min_count=None,
                        max_count=None, security_groups=None, userdata=None,
                        key_name=None, availability_zone=None,
                        block_device_mapping=None,
                        block_device_mapping_v2=None,
                        nics=None, scheduler_hints=None, config_drive=None,
                        disk_config=None, **kwargs):

        nova = novaclient(context, admin=True)

        bdm = block_device_mapping_v2
        return nova.servers.create(name, image,
                                   flavor, meta=meta, files=files,
                                   reservation_id=reservation_id,
                                   min_count=min_count, max_count=max_count,
                                   security_groups=security_groups,
                                   userdata=userdata,
                                   key_name=key_name,
                                   availability_zone=availability_zone,
                                   block_device_mapping=block_device_mapping,
                                   block_device_mapping_v2=bdm,
                                   nics=nics, scheduler_hints=scheduler_hints,
                                   config_drive=config_drive,
                                   disk_config=disk_config,
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

    def interface_attach(self, context, server_id, net_id,
                         port_id=None, fixed_ip=None):
        LOG.debug(_LE("Nova client attach a interface to %s start"), server_id)

        LOG.debug(_LE("Nova client query server %s start"), server_id)
        client = novaclient(context, admin=True)
        server = client.servers.get(server_id)
        LOG.debug(_LE("Nova client query server %s end"), str(server))
        obj = client.servers.interface_attach(server, port_id,
                                              net_id, fixed_ip)
        return obj

    def interface_detach(self, context, server_id, port_id):
        LOG.debug(_LE("Novaclient detach interface from %s start"), server_id)

        LOG.debug(_LE("Nova client query server %s start"), server_id)
        client = novaclient(context, admin=True)
        server = client.servers.get(server_id)
        LOG.debug(_LE("Nova client query server %s end"), str(server))
        return client.servers.interface_detach(server, port_id)

    def associate_floatingip(self, context, server_id,
                             address, fixed_address=None):
        client = novaclient(context, admin=True)
        client.servers.add_floating_ip(server_id, address, fixed_address)

    def migrate_interface_detach(self, context, server_id, port_id):
        client = adminclient(context)
        return client.servers.interface_detach(server_id, port_id)

    def keypair_list(self, context, is_dict=True):
        keypairs = novaclient(context, admin=True).keypairs.list()
        if is_dict:
            keypair_list = []
            for keypair in keypairs:
                keypair = self._dict_keypair(keypair)
                keypair_list.append(keypair)
            return keypair_list
        return keypairs

    def get_keypair(self, context, keypair_id, is_dict=True):
        keypair = novaclient(context, admin=True).keypairs.get(keypair_id)
        if is_dict:
            keypair = self._dict_keypair(keypair)
        return keypair

    def flavor_list(self, context, detailed=True,
                    is_public=True, is_dict=True):
        client = novaclient(context, admin=True)
        flavors = client.flavors.list(detailed=detailed,
                                      is_public=is_public)
        if is_dict:
            flavor_list = []
            for flavor in flavors:
                flavor = self._dict_flavor(flavor)
                flavor_list.append(flavor)
            return flavor_list
        return flavors

    def get_flavor(self, context, flavor_id, is_dict=True):
        flavor = novaclient(context, admin=True).flavors.get(flavor_id)
        if is_dict:
            flavor = self._dict_flavor(flavor)
        return flavor

    def server_security_group_list(self, context, server, is_dict=True):
        client = novaclient(context, admin=True)
        secgroups = client.servers.list_security_group(server)
        if is_dict:
            sec_list = []
            for sec in secgroups:
                sec = self._dict_secgroup(sec)
                sec_list.append(sec)
            return sec_list
        return secgroups

    def availability_zone_list(self, context, detailed=True, is_dict=True):
        client = novaclient(context, admin=True)
        zones = client.availability_zones.list(detailed=detailed)
        if is_dict:
            zones = self._dict_availability_zone(zones)

        return zones

    def reset_state(self, context, server_id, state):
        client = novaclient(context, admin=True)
        server = client.servers.get(server_id)
        return client.servers.reset_state(server, state)

    def stop_server(self, context, server_id):
        return novaclient(context, admin=True).servers.stop(server_id)

    def start_server(self, context, server_id):
        return novaclient(context, admin=True).servers.start(server_id)
