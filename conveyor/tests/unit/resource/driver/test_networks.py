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

from conveyor import context
from conveyor import exception
from conveyor.network import neutron
from conveyor.resource.driver import networks
from conveyor.resource import resource
from conveyor.tests import test

fake_user_id = '01329398-2050-4152-a034-c1b302e70619'
fake_project_id = 'd23b65e027f9461ebe900916c0412ade'

fake_net_dict = {
    "status": "ACTIVE",
    "subnets": [
      "ecc01e23-ed69-4c4a-a93c-6ab3d76e59d8"
    ],
    "availability_zone_hints": [],
    "availability_zones": [],
    "name": "test02",
    "provider:physical_network": None,
    "admin_state_up": True,
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "created_at": "2017-03-27T01:54:49",
    "tags": [],
    "updated_at": "2017-03-27T01:54:49",
    "ipv6_address_scope": None,
    "description": "",
    "router:external": False,
    "provider:network_type": "vxlan",
    "ipv4_address_scope": None,
    "shared": False,
    "mtu": 1450,
    "id": "01329398-2050-4152-a034-c1b302e70619",
    "provider:segmentation_id": 9957
}

fake_subnet_dict = {
    "description": "",
    "enable_dhcp": True,
    "network_id": "2c9f925b-ad53-4cc0-8e16-6e555e01773a",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "created_at": "2017-03-25T02:21:48",
    "dns_nameservers": [],
    "updated_at": "2017-03-25T02:21:48",
    "gateway_ip": "192.168.0.1",
    "ipv6_ra_mode": None,
    "allocation_pools": [
      {
        "start": "192.168.0.2",
        "end": "192.168.15.254"
      }
    ],
    "host_routes": [],
    "ip_version": 4,
    "ipv6_address_mode": None,
    "cidr": "192.168.0.0/20",
    "id": "f49b5787-ef10-4769-8b72-340c04decc92",
    "subnetpool_id": None,
    "name": "subnet-test"
}

fake_port_dict = {
    "status": "DOWN",
    "created_at": "2017-03-25T02:21:49",
    "binding:host_id": "",
    "description": "",
    "allowed_address_pairs": [],
    "admin_state_up": True,
    "network_id": "2c9f925b-ad53-4cc0-8e16-6e555e01773a",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "extra_dhcp_opts": [],
    "updated_at": "2017-03-25T02:21:49",
    "name": "",
    "binding:vif_type": "unbound",
    "device_owner": "network:dhcp",
    "mac_address": "fa:16:3e:39:a2:63",
    "binding:vif_details": {},
    "binding:profile": {},
    "binding:vnic_type": "normal",
    "fixed_ips": [{"subnet_id": "f49b5787-ef10-4769-8b72-340c04decc92",
                   "ip_address": "192.168.0.2"}],
    "id": "91d59727-23df-46cc-95d9-07cbb7d982f9",
    "security_groups": [],
    "device_id": ""
}

fake_secgroup_dict = {
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "description": "Default security group",
    "id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
    "security_group_rules": [
        {
            "direction": "egress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "061e23dd-78d8-47c3-bb6b-4a22f6e8de4e",
            "remote_group_id": None,
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv6"
        },
        {
            "direction": "ingress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "8c44bf1e-c28f-483a-96ed-8c95a5269c3c",
            "remote_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv4"
        },
        {
            "direction": "egress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "df56261d-c9e0-48ea-88a9-b14ec67209a4",
            "remote_group_id": None,
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv4"
        },
        {
            "direction": "ingress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "7957cff7-34e5-4a57-bb0c-cb299a145dd4",
            "remote_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv6"
        }
    ],
    "name": "default"
}


fake_fip_dict = {
    "router_id": None,
    "status": "DOWN",
    "description": "",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "floating_network_id": "01329398-2050-4152-a034-c1b302e70619",
    "fixed_ip_address": None,
    "floating_ip_address": "192.230.1.3",
    "port_id": None,
    "id": "da1efe8d-b91c-475e-a095-e21df9af1a0d"
}


class NetworkResourceTestCase(test.TestCase):

    def setUp(self):
        super(NetworkResourceTestCase, self).setUp()
        self.context = context.RequestContext(fake_user_id, fake_project_id,
                                              is_admin=False)
        self.net_resource = networks.NetworkResource(self.context)

    @mock.patch.object(neutron.API, 'network_list')
    def test_extract_all_nets(self, mock_net_list):
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net_list.return_value = [fake_net]
        result = self.net_resource.extract_nets([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_net['id'], result[0].id)

    @mock.patch.object(neutron.API, 'get_network')
    def test_extract_nets_with_ids(self, mock_net):
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        result = self.net_resource.extract_nets([fake_net['id']])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_net['id'], result[0].id)

    @mock.patch.object(neutron.API, 'get_network', side_effect=Exception)
    def test_extract_nets_failed(self, mock_net):
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_nets,
                          ['net-id'])

    @mock.patch.object(neutron.API, 'network_list')
    def test_extract_nets_from_cache(self, mock_net_list):
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net_list.return_value = [fake_net]
        fake_net_id = fake_net['id']
        fake_net_name = fake_net['name']

        fake_net_res = resource.Resource(fake_net_name,
                                         'OS::Neutron::Net',
                                         fake_net_id)
        fake_net_dep = resource.ResourceDependency(fake_net_id,
                                                   fake_net_name,
                                                   'volume_0',
                                                   'OS::Neutron::Net')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_net_id: fake_net_res},
            collected_dependencies={fake_net_id: fake_net_dep})
        result = self.net_resource.extract_nets([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_net_id, result[0].id)

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_network')
    def test_extract_nets_with_subnets(self, mock_net, mock_subnet):
        # NOTE: evoke extract_nets with parameter with_subnets=True
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_nets([fake_net['id']],
                                                with_subnets=True)
        self.assertTrue(1 == len(result))
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'subnet_list')
    def test_extract_all_subnets(self, mock_subnet_list, mock_net):
        # NOTE: the switch case that retrieve net for this subnet, if
        # returned network_res is None, then the exception will be raised
        # in method extract_nets, so this case will never be evoked.
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet_list.return_value = [fake_subnet]
        mock_net.return_value = copy.deepcopy(fake_net_dict)

        result = self.net_resource.extract_subnets([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_subnet['id'], result[0].id)
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'get_subnet')
    def test_extract_subnets_with_ids(self, mock_subnet, mock_net):
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        mock_net.return_value = copy.deepcopy(fake_net_dict)
        result = self.net_resource.extract_subnets([fake_subnet['id']])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_subnet['id'], result[0].id)
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_subnet', side_effect=Exception)
    def test_extract_subnets_failed(self, mock_subnet):
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_subnets,
                          ['subnet_123'])

    @mock.patch.object(neutron.API, 'subnet_list')
    def test_extract_subnets_from_cache(self, mock_subnet_list):
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        fake_subnet_id = fake_subnet['id']
        fake_subnet_name = fake_subnet['name']
        mock_subnet_list.return_value = [fake_subnet]
        fake_subnet_res = resource.Resource(fake_subnet_name,
                                            'OS::Neutron::Subnet',
                                            fake_subnet_id)
        fake_subnet_dep = resource.ResourceDependency(fake_subnet_id,
                                                      fake_subnet_name,
                                                      'subnet_0',
                                                      'OS::Neutron::Subnet')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_subnet_id: fake_subnet_res},
            collected_dependencies={fake_subnet_id: fake_subnet_dep}
        )
        result = self.net_resource.extract_subnets([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_subnet_id, result[0].id)
        self.assertTrue(1 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'port_list')
    def test_extract_all_ports(self, mock_port_list, mock_subnet):
        # NOTE: default, in the case, subnets will be extracted.
        fake_port = copy.deepcopy(fake_port_dict)
        mock_port_list.return_value = [fake_port]

        fake_subnet = copy.deepcopy(fake_subnet_dict)
        fake_subnet_id = fake_subnet['id']
        fake_subnet_name = fake_subnet['name']
        mock_subnet.return_value = fake_subnet

        fake_subnet_res = resource.Resource(
            fake_subnet_name,
            'OS::Neutron::Subnet',
            fake_subnet_id,
            properties={
                'network_id': {'get_resource': 'network_0'}
            })
        fake_subnet_dep = resource.ResourceDependency(fake_subnet_id,
                                                      fake_subnet_name,
                                                      'subnet_0',
                                                      'OS::Neutron::Subnet')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_subnet_id: fake_subnet_res},
            collected_dependencies={fake_subnet_id: fake_subnet_dep}
        )

        result = self.net_resource.extract_ports([])
        self.assertTrue(1 == len(result))
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_with_ids(self, mock_port, mock_subnet):
        # NOTE: default, in the case, subnets will be extracted.
        fake_port = copy.deepcopy(fake_port_dict)
        mock_port.return_value = fake_port

        fake_subnet = copy.deepcopy(fake_subnet_dict)
        fake_subnet_id = fake_subnet['id']
        fake_subnet_name = fake_subnet['name']
        mock_subnet.return_value = fake_subnet

        fake_subnet_res = resource.Resource(
            fake_subnet_name,
            'OS::Neutron::Subnet',
            fake_subnet_id,
            properties={
                'network_id': {'get_resource': 'network_0'}
            })
        fake_subnet_dep = resource.ResourceDependency(fake_subnet_id,
                                                      fake_subnet_name,
                                                      'subnet_0',
                                                      'OS::Neutron::Subnet')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_subnet_id: fake_subnet_res},
            collected_dependencies={fake_subnet_id: fake_subnet_dep}
        )

        result = self.net_resource.extract_ports([fake_port['id']])
        self.assertTrue(1 == len(result))
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_failed(self, mock_port):
        fake_port = copy.deepcopy(fake_port_dict)
        mock_port.return_value = fake_port
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_ports,
                          [fake_port['id']])

    @mock.patch.object(neutron.API, 'port_list')
    def test_extract_ports_from_cache(self, mock_port_list):
        fake_port = copy.deepcopy(fake_port_dict)
        mock_port_list.return_value = [fake_port]
        fake_port_id = fake_port['id']
        fake_port_name = fake_port['name']
        fake_port_des = resource.Resource(fake_port_name, 'OS::Neutron::Port',
                                          fake_port_id)
        fake_port_dep = resource.ResourceDependency(fake_port_id,
                                                    fake_port_name,
                                                    'port_0',
                                                    'OS::Neutron::Port')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_port_id: fake_port_des},
            collected_dependencies={fake_port_id: fake_port_dep})
        result = self.net_resource.extract_ports([])
        self.assertTrue(1 == len(result))
        self.assertTrue(1 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_security_group')
    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_with_secgroups(self, mock_port, mock_secgroup):
        # NOTE: this test will open the switch case
        # `if port.get('security_groups')`
        fake_port = copy.deepcopy(fake_port_dict)
        fake_port['security_groups'] = ['164c7126-ee4e-44e8-afb5-cc2f11225b30']
        fake_port['fixed_ips'] = []
        mock_port.return_value = fake_port
        mock_secgroup.return_value = copy.deepcopy((fake_secgroup_dict))
        result = self.net_resource.extract_ports([fake_port['id']])
        self.assertTrue(1 == len(result))
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_with_invalid_ips(self, mock_port):
        fake_port = copy.deepcopy(fake_port_dict)
        fake_port['fixed_ips'] = [{}]
        mock_port.return_value = fake_port
        self.assertRaises(exception.ResourceAttributesException,
                          self.net_resource.extract_ports,
                          [fake_port['id']])

    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_without_subnet(self, mock_port):
        # NOTE: for switch case: self.extract_subnets, the returned subnets
        # would not be None, so this case is not reachable
        # TODO(drngsl)
        pass

    @mock.patch.object(neutron.API, 'secgroup_list')
    def test_extract_all_secgroups(self, mock_secgroup_list):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup_list.return_value = [fake_secgroup]
        result = self.net_resource.extract_secgroups([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_secgroup['id'], result[0].id)
        self.assertTrue(
            1 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_security_group')
    def test_extract_secgroups_with_ids(self, mock_secgroup):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup.return_value = fake_secgroup
        fake_sg_id = fake_secgroup['id']
        result = self.net_resource.extract_secgroups([fake_sg_id])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_sg_id, result[0].id)
        self.assertTrue(
            1 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'secgroup_list')
    def test_extract_secgroups_from_cache(self, mock_secgroup_list):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup_list.return_value = [fake_secgroup]
        fake_sg_id = fake_secgroup['id']
        fake_sg_name = fake_secgroup['name']

        fake_net_res = resource.Resource(fake_sg_name,
                                         'OS::Neutron::SecurityGroup',
                                         fake_sg_id)
        fake_net_dep = resource.ResourceDependency(
            fake_sg_id, fake_sg_name, 'securitygroup_0',
            'OS::Neutron::SecurityGroup')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_sg_id: fake_net_res},
            collected_dependencies={fake_sg_id: fake_net_dep})
        result = self.net_resource.extract_secgroups([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_sg_id, result[0].id)

    @mock.patch.object(neutron.API, 'get_security_group',
                       side_effect=Exception)
    def test_extract_secgroups_failed(self, mock_secgroup):
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_secgroups,
                          ['sg_123'])

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_all_fips(self, mock_fip_list, mock_net, mock_subnet):
        # NOTE: This test only extracts net and subnet for fip while without
        # router and port.
        fake_fip = copy.deepcopy(fake_fip_dict)
        mock_fip_list.return_value = [fake_fip]
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_floatingips([])
        self.assertTrue(1 == len(result))
        self.assertTrue(3 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'get_floatingip')
    def test_extract_fips_with_ids(self, mock_fip, mock_net, mock_subnet):
        fake_fip = copy.deepcopy(fake_fip_dict)
        mock_fip.return_value = fake_fip
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_floatingips([fake_fip['id']])
        self.assertTrue(1 == len(result))
        self.assertTrue(3 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_floatingip', side_effect=Exception)
    def test_extract_fips_failed(self, mock_fip):
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_floatingips,
                          [fake_fip_dict['id']])

    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_fips_from_cache(self, mock_fip_list):
        fake_fip = copy.deepcopy(fake_fip_dict)
        mock_fip_list.return_value = [fake_fip]
        fake_fip_id = fake_fip['id']
        fake_fip_name = ''
        fake_fip_res = resource.Resource(fake_fip_name,
                                         'OS::Neutron::FloatingIP',
                                         fake_fip_id)
        fake_fip_dep = resource.ResourceDependency(fake_fip_id,
                                                   fake_fip_name,
                                                   'floatingip_0',
                                                   'OS::Neutron::FloatingIP')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_fip_id: fake_fip_res},
            collected_dependencies={fake_fip_id: fake_fip_dep})
        result = self.net_resource.extract_floatingips([])
        self.assertTrue(1 == len(result))
        self.assertTrue(1 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_fips_with_invalid_ip(self, mock_fip_list):
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_ip_address'] = ''
        mock_fip_list.return_value = [fake_fip]
        self.assertRaises(exception.ResourceAttributesException,
                          self.net_resource.extract_floatingips,
                          [])

    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_fips_with_invalid_net(self, mock_fip_list):
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_network_id'] = ''
        mock_fip_list.return_value = [fake_fip]
        self.assertRaises(exception.ResourceAttributesException,
                          self.net_resource.extract_floatingips,
                          [])

    def test_extract_fips_with_router(self):
        # TODO(drngsl)
        pass

    @mock.patch.object(neutron.API, 'get_port')
    @mock.patch.object(neutron.API, 'get_floatingip')
    def test_extract_fips_with_port(self, mock_fip, mock_port):
        # TODO(drngsl)
        # fake_fip = copy.deepcopy(fake_fip_dict)
        # mock_fip.return_value = fake_fip
        # fake_port = copy.deepcopy(fake_port_dict)
        # mock_port.return_value = fake_port
        # fake_port_id = fake_port['id']
        # fake_port_name = fake_port['name']
        # fake_port_des = resource.Resource(fake_port_name,
        #                                   'OS::Neutron::Port',
        #                                   fake_port_id)
        # fake_port_dep = resource.ResourceDependency(fake_port_id,
        #                                             fake_port_name,
        #                                             'port_0',
        #                                             'OS::Neutron::Port')
        # self.net_resource = networks.NetworkResource(
        #     self.context,
        #     collected_resources={fake_port_id: fake_port_des},
        #     collected_dependencies={fake_port_id: fake_port_dep})
        # result = self.net_resource.extract_floatingips([fake_fip['id']])
        # self.assertTrue(1 == len(result))
        # self.assertTrue(
        #     2 == len(self.net_resource.get_collected_resources()))
        pass
