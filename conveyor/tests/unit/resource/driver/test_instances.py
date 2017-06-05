# Copyright (c) 2017 Huawei, Inc.
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

import copy
import mock

from conveyor.compute import nova
from conveyor import context
from conveyor import exception
from conveyor.network import neutron
from conveyor.resource.driver import instances
from conveyor.resource.driver import networks
from conveyor.resource import resource
from conveyor.tests import test


fake_server_dict = {
    "id": "server_123",
    "name": "ubuntu14.04",
    "OS-EXT-STS:vm_state": "stopped",
    "OS-EXT-STS:power_state": 4,
    "metadata": {},
    "OS-EXT-SRV-ATTR:user_data": "",
    "image": {"id": "image_123"},
    "flavor": {"id": "6"},
    "addresses": {"test02": [{
        "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:e5:66:fc",
        "version": 4,
        "addr": "197.168.16.56",
        "OS-EXT-IPS:type": "fixed"}
    ]},
    "key_name": "keypair_123",
    "os-extended-volumes:volumes_attached": '',
    "OS-EXT-AZ:availability_zone": "az01",
    'status': 'stopped'
}

fake_flavor_dict = {
    "id": 6,
    "name": '',
    "ram": 1024,
    "vcpus": 1,
    "disk": 5,
    "rxtx_factor": 1,
    "os-flavor-access:is_public": True,
    "OS-FLV-EXT-DATA:ephemeral": 0,
}

fake_keypair_dict = {
    "id": "keypair_123",
    "name": "keyapir",
    "public_key": "public_key"
}


fake_port_dict = {
    "status": "UP",
    "created_at": "2017-04-24T12:32:10",
    "binding:host_id": "",
    "description": "",
    "allowed_address_pairs": [],
    "admin_state_up": True,
    "network_id": "01329398-2050-4152-a034-c1b302e70619",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "extra_dhcp_opts": [],
    "updated_at": "2017-04-24T13:06:34",
    "name": "",
    "binding:vif_type": "unbound", "device_owner": "",
    "mac_address": "fa:16:3e:e5:66:fc", "binding:vif_details": {},
    "binding:profile": {},
    "binding:vnic_type": "normal",
    "fixed_ips": [{"subnet_id": "ecc01e23-ed69-4c4a-a93c-6ab3d76e59d8",
                   "ip_address": "197.168.16.56"}],
    "id": "00c94695-077e-4b2d-9858-f902e4f6a932",
    "security_groups": ["6207c842-f8a1-4ce7-9931-acfbe7929df1"],
    "device_id": ""
}


class InstanceResourceTesetCase(test.TestCase):

    def setUp(self):
        super(InstanceResourceTesetCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.instance_resource = instances.InstanceResource(self.context)

    @mock.patch.object(networks.NetworkResource, 'extract_ports')
    @mock.patch.object(neutron.API, 'port_list')
    @mock.patch.object(nova.API, 'get_keypair')
    @mock.patch.object(nova.API, 'get_flavor')
    @mock.patch.object(nova.API, 'get_all_servers')
    def test_extract_all_instances(self, mock_server_list, mock_flavor,
                                   mock_keypair, mock_port_list,
                                   mock_extract_ports):
        # NOTE: for extracting servers, the following resources may be need
        # to extract: flavor, keypair, image, volume, network.
        mock_server_list.return_value = [copy.deepcopy(fake_server_dict)]
        mock_flavor.return_value = copy.deepcopy(fake_flavor_dict)
        mock_keypair.return_value = copy.deepcopy(fake_keypair_dict)
        mock_port_list.return_value = [copy.deepcopy(fake_port_dict)]
        mock_extract_ports.return_value = [
            resource.Resource('port_0', 'OS::Neutron::Port',
                              '00c94695-077e-4b2d-9858-f902e4f6a932')
        ]
        self.instance_resource.extract_instances([])
        self.assertTrue(
            len(self.instance_resource.get_collected_resources()) >= 3)

    @mock.patch.object(nova.API, 'get_all_servers')
    def test_extract_instance_with_no_servers(self, mock_server_list):
        mock_server_list.return_value = []
        self.instance_resource.extract_instances([])
        self.assertEqual(0,
                         len(self.instance_resource.get_collected_resources()))

    @mock.patch.object(nova.API, 'get_all_servers')
    def tet_extract_instance_with_invalid_addresses(self, mock_server_list):
        fake_server = copy.deepcopy(fake_server_dict)
        fake_server.pop("image")
        fake_server.pop("flavor")
        fake_server.pop("os-extended-volumes:volumes_attached")
        fake_server.pop("addresses")
        mock_server_list.return_value = [fake_server]
        self.assertRaises(exception.ResourceAttributesException,
                          self.instance_resource.extract_instances,
                          [])

    @mock.patch.object(nova.API, 'get_all_servers')
    def test_extract_instance_with_not_allowed_status(self, mock_server_list):
        fake_server = copy.deepcopy(fake_server_dict)
        fake_server.update({"OS-EXT-STS:vm_state": "error", 'status': 'error'})
        mock_server_list.return_value = [fake_server]
        self.assertRaises(exception.PlanCreateFailed,
                          self.instance_resource.extract_instances,
                          [])

    @mock.patch.object(networks.NetworkResource, 'extract_ports')
    @mock.patch.object(neutron.API, 'port_list')
    @mock.patch.object(nova.API, 'get_keypair')
    @mock.patch.object(nova.API, 'get_flavor')
    @mock.patch.object(nova.API, 'get_server')
    def test_extract_instances_with_ids(
            self, mock_server, mock_flavor, mock_keypair, mock_port_list,
            mock_extract_ports):
        # NOTE: for extracting servers, the following resources may be need
        # to extract: flavor, keypair, image, volume, network.
        mock_server.return_value = copy.deepcopy(fake_server_dict)
        mock_flavor.return_value = copy.deepcopy(fake_flavor_dict)
        mock_keypair.return_value = copy.deepcopy(fake_keypair_dict)
        mock_port_list.return_value = [copy.deepcopy(fake_port_dict)]
        mock_extract_ports.return_value = [
            resource.Resource('port_0', 'OS::Neutron::Port',
                              '00c94695-077e-4b2d-9858-f902e4f6a932')
        ]
        self.instance_resource.extract_instances([fake_server_dict["id"]])
        self.assertTrue(
            len(self.instance_resource.get_collected_resources()) >= 3)

    @mock.patch.object(nova.API, 'flavor_list')
    def test_extract_all_flavors(self, mock_flavor_list):
        mock_flavor_list.return_value = [{
            "id": 6,
            "name": '',
            "ram": 1024,
            "vcpus": 1,
            "disk": 5,
            "rxtx_factor": 1,
            "os-flavor-access:is_public": True,
            "OS-FLV-EXT-DATA:ephemeral": 0,
        }]
        flavor_res = self.instance_resource.extract_flavors([])
        self.assertEqual(1, len(flavor_res))
        self.assertIn(6, self.instance_resource.get_collected_resources())
        self.assertIn(6, self.instance_resource.get_collected_dependencies())

    @mock.patch.object(nova.API, 'get_flavor')
    def test_extract_flavor_with_ids(self, mock_get_flavor):
        mock_get_flavor.return_value = {
            "id": 6,
            "name": '',
            "ram": 1024,
            "vcpus": 1,
            "disk": 5,
            "rxtx_factor": 1,
            "os-flavor-access:is_public": True,
            "OS-FLV-EXT-DATA:ephemeral": 0,
        }
        flavor_res = self.instance_resource.extract_flavors([6])
        self.assertEqual(1, len(flavor_res))
        self.assertIn(6, self.instance_resource.get_collected_resources())
        self.assertIn(6, self.instance_resource.get_collected_dependencies())

    @mock.patch.object(nova.API, 'flavor_list')
    @mock.patch.object(resource, 'Resource')
    def test_extract_flavor_from_cache(self, mock_res, mock_flavor_list):
        """The request flavors ia already in collected resources"""
        fake_flavor = {
            "id": 6,
            "name": "flavor_0",
            "type": "OS::Nova::Flavor"
        }
        fake_flavor_res = resource.Resource(**fake_flavor)
        fake_flavor_dep = resource.ResourceDependency(
            6, 'flavor_0', "flavor_0", "OS::Nova::Flavor")
        self.instance_resource = instances.InstanceResource(
            self.context,
            collected_resources={6: fake_flavor_res},
            collected_dependencies={6: fake_flavor_dep})
        mock_flavor_list.return_value = [{
            "id": 6,
            "name": '',
            "ram": 1024,
            "vcpus": 1,
            "disk": 5,
            "rxtx_factor": 1,
            "os-flavor-access:is_public": True,
            "OS-FLV-EXT-DATA:ephemeral": 0,
        }]

        flavor_res = self.instance_resource.extract_flavors([])
        self.assertEqual(1, len(flavor_res))

    @mock.patch.object(nova.API, 'get_flavor', side_effect=Exception)
    def test_extract_flavor_failed(self, mock_get_flavor):
        self.assertRaises(exception.ResourceNotFound,
                          self.instance_resource.extract_flavors,
                          [6])

    @mock.patch.object(nova.API, 'keypair_list')
    def test_extract_all_keypairs(self, mock_keypair_list):
        # NOTE: This test no support input parameter, and inited
        # instnace_resource does not contain any collected resources or
        # dependencies.
        mock_keypair_list.return_value = [
            {
                "id": "keypair_0",
                "name": "keyapir",
                "public_key": "public_key"
            }
        ]

        keypair_res = self.instance_resource.extract_keypairs([])
        self.assertEqual(1, len(keypair_res))
        self.assertIn('keypair_0',
                      self.instance_resource.get_collected_resources())
        self.assertIn('keypair_0',
                      self.instance_resource.get_collected_dependencies())

    @mock.patch.object(nova.API, 'get_keypair')
    def test_extract_keypairs_with_ids(self, mock_get_keypair):
        mock_get_keypair.return_value = {
            "id": "keypair_0",
            "name": "keyapir",
            "public_key": "public_key"
        }

        fake_keypair_ids = ['keypair_0']
        keypair_res = self.instance_resource.extract_keypairs(fake_keypair_ids)
        self.assertEqual(1, len(keypair_res))
        self.assertIn('keypair_0',
                      self.instance_resource.get_collected_resources())
        self.assertIn('keypair_0',
                      self.instance_resource.get_collected_dependencies())

    @mock.patch.object(nova.API, 'keypair_list')
    @mock.patch.object(resource, 'Resource')
    def test_extract_keypairs_from_cache(self, mock_res, mock_keypair_list):
        """The request keypair ia already in collected resources"""
        fake_keypair = {
            "id": "keypair_0",
            "name": "keypair_0",
            "type": "OS::Nova::KeyPair"
        }
        fake_keypair_res = resource.Resource(**fake_keypair)
        fake_keypair_dep = resource.ResourceDependency(
            "keypair_0", "keypair_0", "keypair_0", "OS::Nova::KeyPair")
        self.instance_resource = instances.InstanceResource(
            self.context,
            collected_resources={'keypair_0': fake_keypair_res},
            collected_dependencies={'keypair_0': fake_keypair_dep})
        mock_keypair_list.return_value = [
            {
                "id": "keypair_0",
                "name": "keyapir",
                "public_key": "public_key"
            }
        ]

        keypair_res = self.instance_resource.extract_keypairs([])
        self.assertEqual(1, len(keypair_res))

    def test_extract_keyapirs_failed(self):
        with mock.patch.object(nova.API, 'get_keypair', side_effect=Exception):
            self.assertRaises(exception.ResourceNotFound,
                              self.instance_resource.extract_keypairs,
                              ['keypair_0'])

    def test_extract_image(self):
        fake_image_id = "image_123"
        result = self.instance_resource.extract_image(fake_image_id)
        self.assertIsNotNone(result)
        self.assertIn(fake_image_id,
                      self.instance_resource._collected_parameters)
