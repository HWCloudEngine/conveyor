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

from conveyor import exception

from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor.i18n import _LE
from conveyor.resource import resource
from conveyor.resource.driver import base
from conveyor.resource.driver.volumes import VolumeResource
from conveyor.resource.driver.networks import NetworkResource

from oslo_log import log as logging
LOG = logging.getLogger(__name__)


class InstanceResource(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}
        self.nova_api = compute.API()
        self.cinder_api = volume.API()
        self.neutron_api = network.API()

    def extract_instances(self, instance_ids=None):

        instance_reses = []
        servers = []
        if not instance_ids:
            LOG.info('Get resources of all instances.')
            servers = self.nova_api.get_all_servers(self.context)
        else:
            LOG.info('Get resources of instance: %s', instance_ids)
            for instance_id in instance_ids:
                try:
                    server = self.nova_api.get_server(self.context,
                                                      instance_id)
                    servers.append(server)
                except Exception as e:
                    msg = "Instance resource <%s> could not be found. %s" \
                            % (instance_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for server in servers:
            res = self._extract_single_instance(server)
            instance_reses.append(res)

    def _extract_single_instance(self, server):

        if not server:
            return

        instance_id = server.get('id', '')
        LOG.debug('Extract resources of instance %s.', instance_id)

        # If this server resource has been extracted, ignore it.
        instance_resources = self._collected_resources.get(instance_id)
        if instance_resources:
            return instance_resources

        resource_type = "OS::Nova::Server"
        resource_name = "server_%d" % self._get_resource_num(resource_type)
        instance_resources = resource.Resource(resource_name, resource_type,
                                               instance_id, properties={})

        name = server.get('name', None)
        instance_dependencies = resource.ResourceDependency(instance_id, name,
                                                            resource_name,
                                                            resource_type)

        instance_resources.add_property('name', name)
        availability_zone = server.get('OS-EXT-AZ:availability_zone', '')
        instance_resources.add_property('availability_zone', availability_zone)

        # extract metadata parameter.
        # If metadata is None, ignore this parameter.
        metadata = server.get('metadata', {})
        if metadata:
            instance_resources.add_property('metadata', metadata)

        # extract userdata parameter.
        # If userdata is None, ignore this parameter.
        user_data = server.get('OS-EXT-SRV-ATTR:user_data', '')
        if user_data:
            instance_resources.add_property('user_data', user_data)
            instance_resources.add_property('user_data_format', 'RAW')

        # extract flavor resource, if failed, raise exception
        flavor = server.get('flavor', {})
        if flavor and flavor.get('id'):
            flavor_id = flavor.get('id')
            try:
                flavor_res = self.extract_flavors([flavor_id])
                instance_resources.add_property('flavor',
                                                {'get_resource': flavor_res[0].name})
                instance_dependencies.add_dependency(flavor_res[0].name)
            except Exception as e:
                msg = "Instance flavor resource extracted failed. %s" % unicode(e)
                LOG.error(msg)
                # TODO  get flavor resource by another method
                raise exception.ResourceNotFound(message=msg)

        # extract keypair resource, if failed, give up this resource
        keypair_name = server.get('key_name', '')
        if keypair_name:
            try:
                keypair_res = self.extract_keypairs([keypair_name])
                instance_resources.add_property('key_name', {'get_resource': keypair_res[0].name})
                instance_dependencies.add_dependency(keypair_res[0].name)
            except Exception as e:
                msg = "Instance keypair resource extracted failed. %s" % unicode(e)
                LOG.error(msg)
                raise exception.ResourceNotFound(message=msg)

        # extract image parameter
        image = server.get('image', '')
        if image and image.get('id'):
            image_id = image.get('id')
            image_para_name = self.extract_image(image_id)
            description = ("Image to use to boot server or volume")
            constraints = [{'custom_constraint': "glance.image"}]
            instance_resources.add_parameter(image_para_name, description,
                                             default=image_id,
                                             constraints=constraints)
            instance_resources.add_property('image', {'get_param': image_para_name})

        # extract bdm resources
        volumes_attached = server.get('os-extended-volumes:volumes_attached',
                                      '')
        if volumes_attached:
            self._build_vm_bdm(server, instance_resources,
                               instance_dependencies)

        # extract network resources
        addresses = server.get('addresses', {})
        if addresses:
            self._build_vm_networks(server,
                                    instance_resources,
                                    instance_dependencies)
        else:
            msg = "Instance addresses information is abnormal. \
                    'addresses' attribute is None"
            LOG.error(msg)
            raise exception.ResourceAttributesException(message=msg)

        # add extra properties
        vm_state = server.get('OS-EXT-STS:vm_state', None)
        instance_resources.add_extra_property('vm_state', vm_state)

        power_state = server.get('OS-EXT-STS:power_state', None)
        instance_resources.add_extra_property('power_state', power_state)
        LOG.info('Extracting instance %s has finished', instance_id)

        self._collected_resources[instance_id] = instance_resources
        self._collected_dependencies[instance_id] = instance_dependencies

        return instance_resources

    def extract_flavors(self, flavor_ids):

        flavor_objs = []
        flavorResources = []

        if not flavor_ids:
            LOG.debug('Extract resources of all flavors.')
            flavor_objs = self.nova_api.flavor_list(self.context)
        else:
            LOG.debug('Extract resources of flavors: %s', flavor_ids)
            # remove duplicate flavors
            flavor_ids = {}.fromkeys(flavor_ids).keys()
            for flavor_id in flavor_ids:
                try:
                    flavor = self.nova_api.get_flavor(self.context, flavor_id)
                    flavor_objs.append(flavor)
                except Exception as e:
                    msg = "Flavor resource <%s> could not be found. %s" \
                            % (flavor_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for flavor in flavor_objs:
            resource_id = flavor.get('id', '')
            flavor_res = self._collected_resources.get(resource_id)
            if flavor_res:
                flavorResources.append(flavor_res)
                continue

            ram = flavor.get('ram', '')
            vcpus = flavor.get('vcpus', '')
            disk = flavor.get('disk', '')
            ephemeral = flavor.get('OS-FLV-EXT-DATA:ephemeral', '')
            rxtx_factor = flavor.get('rxtx_factor', '')
            is_public = flavor.get('os-flavor-access:is_public', '')

            properties = {'ram': ram,
                          'vcpus': vcpus,
                          'disk': disk,
                          'ephemeral': ephemeral,
                          'rxtx_factor': rxtx_factor,
                          'is_public': is_public
                          }

            keys = flavor.get('keys', '')
            if keys:
                properties['extra_specs'] = keys

            swap = flavor.get('swap', '')
            if swap:
                properties['swap'] = swap

            resource_type = "OS::Nova::Flavor"
            resource_name = "flavor_%d" % self._get_resource_num(resource_type)
            flavor_res = resource.Resource(resource_name, resource_type,
                                           resource_id, properties=properties)
            flavor_dep = resource.ResourceDependency(resource_id, flavor.name,
                                                     resource_name,
                                                     resource_type)

            self._collected_resources[resource_id] = flavor_res
            self._collected_dependencies[resource_id] = flavor_dep
            flavorResources.append(flavor_res)

        if flavor_ids and not flavorResources:
            msg = "Flavor resource extracted failed, \
                    can't find the flavor with id of %s." % flavor_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        return flavorResources

    def extract_keypairs(self, keypair_ids):

        keypair_objs = []
        keypairResources = []

        if not keypair_ids:
            LOG.debug('Extract resources of all keypairs.')
            keypair_objs = self.nova_api.keypair_list(self.context)
        else:
            LOG.debug('Extract resources of keypairs: %s', keypair_ids)
            # remove duplicate keypairs
            keypair_ids = {}.fromkeys(keypair_ids).keys()
            for keypair_id in keypair_ids:
                try:
                    keypair = self.nova_api.get_keypair(self.context,
                                                        keypair_id)
                    keypair_objs.append(keypair)
                except Exception as e:
                    msg = "Keypair resource <%s> could not be found. %s" \
                            % (keypair_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for keypair in keypair_objs:
            resource_id = keypair.get('id', '')
            keypair_res = self._collected_resources.get(resource_id)
            if keypair_res:
                keypairResources.append(keypair_res)
                continue

            name = keypair.get('name', '')
            properties = {'name': name,
                          'public_key': keypair.get('public_key', '')
                          }

            resource_type = "OS::Nova::KeyPair"
            resource_name = "keypair_%d" \
                % self._get_resource_num(resource_type)
            keypair_res = resource.Resource(resource_name, resource_type,
                                            resource_id, properties=properties)
            keypair_dep = resource.ResourceDependency(resource_id,
                                                      name,
                                                      resource_name,
                                                      resource_type)

            self._collected_resources[resource_id] = keypair_res
            self._collected_dependencies[resource_id] = keypair_dep
            keypairResources.append(keypair_res)

        if keypair_ids and not keypairResources:
            msg = "KeyPair resource extracted failed, \
                    can't find the keypair with id of %s." % keypair_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        return keypairResources

    def _build_vm_secgroups(self, server,
                            instance_resources,
                            instance_dependencies):

        server_id = server.get('id')
        LOG.debug('Extract security group of instance: %s.', server_id)

        try:
            secgroup_objs = self.nova_api.server_security_group_list(self.context,
                                                                     server)
        except Exception as e:
            msg = "Security groups of instance <%s> could not be found. %s" \
                    % (server_id, unicode(e))
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        secgroup_id_list = []

        for sec in secgroup_objs:
            secgroup_id_list.append(sec.get('id'))

        collected_dependencies = self._collected_dependencies
        nr = NetworkResource(self.context,
                             collected_resources=self._collected_resources,
                             collected_parameters=self._collected_parameters,
                             collected_dependencies=collected_dependencies)

        try:
            secgroups__res = nr.extract_secgroups(secgroup_id_list)
            sec_property = []
            for sec in secgroups__res:
                sec_property.append({'get_resource': sec.get('name')})
                instance_dependencies.add_dependency(sec.get('name'))
            if sec_property:
                instance_resources.add_property('security_groups',
                                                sec_property)
        except Exception as e:
            msg = "Instance security group extracted failed. %s" % unicode(e)
            LOG.error(msg)

    def _build_vm_bdm(self, server, instance_resources, instance_dependencies):

        server_id = server.get('id', '')

        LOG.debug(_LE('Extract bdm resources of instance: %s.'), server_id)

        volumes = server.get('os-extended-volumes:volumes_attached', [])

        volume_ids = []

        for v in volumes:
            if v.get('id'):
                volume_ids.append(v.get('id'))

        if len(volume_ids) == 0:
            return

        bdm_property = []
        collected_dependencies = self._collected_dependencies

        vr = VolumeResource(self.context,
                            collected_resources=self._collected_resources,
                            collected_parameters=self._collected_parameters,
                            collected_dependencies=collected_dependencies)

        volume_res = vr.extract_volumes(volume_ids)

        # TODO  get bdm from nova api
        index = 0
        for v in volume_res:
            sys_boot_index = v.extra_properties.get('boot_index', None)
            if sys_boot_index == 0 or sys_boot_index == '0':
                boot_index = sys_boot_index
            else:
                boot_index = index+1
                index += 1
            properties = {'volume_id': {'get_resource': v.name},
                          'boot_index': boot_index}

            instance_dependencies.add_dependency(v.name)

            try:
                volume_dict = self.cinder_api.get(self.context, v.id)
            except Exception as e:
                msg = "Instance volume <%s> could not be found. %s" \
                        % (v.id, unicode(e))
                LOG.error(msg)
                raise exception.ResourceNotFound(message=msg)

            if volume_dict.get('mountpoint'):
                properties['device_name'] = volume_dict['mountpoint']

            bdm_property.append(properties)

        instance_resources.add_property('block_device_mapping_v2',
                                        bdm_property)

    def _build_vm_networks(self, server,
                           instance_resources,
                           instance_dependencies):

        server_id = server.get('id', '')
        LOG.debug('Extract network resources of instance: %s.', server_id)

        addresses = server.get('addresses', {})
        network_properties = []

        fixed_ip_macs = []
        for addrs in addresses.values():
            for addr_info in addrs:
                addr = addr_info.get('addr')
                mac = addr_info.get('OS-EXT-IPS-MAC:mac_addr')
                ip_type = addr_info.get('OS-EXT-IPS:type')

                if not addr or not mac or not ip_type:
                    msg = "Instance addresses information is abnormal. \
                            'addr' or 'mac' or 'type' attribute is None"
                    LOG.error(msg)
                    raise exception.ResourceAttributesException(message=msg)

                nr = NetworkResource(self.context,
                                     collected_resources=self._collected_resources,
                                     collected_parameters=self._collected_parameters,
                                     collected_dependencies=self._collected_dependencies)

                if ip_type == 'fixed':
                    # Avoid the port with different ips was extract many times.
                    if mac in fixed_ip_macs:
                        continue
                    else:
                        fixed_ip_macs.append(mac)

                    port = self.neutron_api.port_list(self.context,
                                                      mac_address=mac)
                    if not port:
                        msg = "Instance network extracted failed, can't find \
                               the port with mac_address of %s." % mac
                        LOG.error(msg)
                        raise exception.ResourceNotFound(message=msg)

                    port_id = port[0].get('id')
                    port_res = nr.extract_ports([port_id])

                    network_properties.append({"port": {"get_resource": port_res[0].name}})
                    instance_dependencies.add_dependency(port_res[0].name)

                elif ip_type == 'floating':
                    floatingip = self.neutron_api.floatingip_list(self.context,
                                                                  floating_ip_address=addr)
                    if not floatingip:
                        msg = "Instance floatingip resource extracted failed, \
                               can't find the floatingip with address of %s." % addr
                        LOG.error(msg)
                        raise exception.ResourceNotFound(message=msg)

                    floatingip_id = floatingip[0].get('id')
                    nr.extract_floatingips([floatingip_id])

        instance_resources.add_property('networks', network_properties)

    def extract_image(self, image_id):

        parameter_name = self._collected_parameters.get(image_id)

        if not parameter_name:
            parameter_name = "image_%d" % self._get_parameter_num()
            self._collected_parameters[image_id] = parameter_name

        return parameter_name
