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

from oslo_utils import uuidutils

from conveyor import context
from conveyor import exception
from conveyor.network import neutron
from conveyor.resource.driver import networks
from conveyor.resource.driver import secgroup
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object

fake_net_dict = fake_object.fake_net_dict
fake_subnet_dict = fake_object.fake_subnet_dict
fake_port_dict = fake_object.fake_port_dict
fake_secgroup_dict = fake_object.fake_secgroup_dict
fake_fip_dict = fake_object.fake_fip_dict
fake_route_dict = fake_object.fake_router_dict

# resource_id for test extract_network_resource
net_0_id = 'net-0'
sb_of_net_0_id = 'net-0-subnet-0'
other_net_id = 'net-1'
sb_of_other_net_id = 'net-1-subnet-1'

# fake external net and subnet id
ext_net_id = 'ext-net'
ext_subnet_id = 'ext-subnet'


def mock_new_net(cls, context, network_id, timeout=None, **_params):
    fake_net = copy.deepcopy(fake_net_dict)
    fake_net['id'] = network_id
    if network_id == net_0_id:
        fake_net['subnets'] = [sb_of_net_0_id]
    elif network_id == other_net_id:
        fake_net['subnets'] = [sb_of_other_net_id]
    elif network_id == ext_net_id:
        fake_net['subnets'] = [ext_subnet_id]

    return fake_net


def mock_new_subnet(cls, context, subnet_id, **_params):
    fake_subnet = copy.deepcopy(fake_subnet_dict)
    fake_subnet['id'] = subnet_id
    if subnet_id == sb_of_net_0_id:
        fake_subnet['network_id'] = net_0_id
    elif subnet_id == sb_of_other_net_id:
        fake_subnet['network_id'] = other_net_id
    elif subnet_id == ext_subnet_id:
        fake_subnet['network_id'] = ext_net_id
    return fake_subnet


def mock_extract_secgroups(cls, secgroups_ids):
    secgroup_res = []
    for secgroup_id in secgroups_ids:
        fake_secgroup = copy.deepcopy(fake_object.fake_secgroup_dict)
        fake_secgroup['id'] = secgroup_id
        name_in_tmpl = uuidutils.generate_uuid()
        sg_res = resource.Resource(name_in_tmpl,
                                   'OS::Neutron::SecurityGroup',
                                   secgroup_id)
        sg_dep = resource.ResourceDependency(secgroup_id,
                                             fake_secgroup['name'],
                                             name_in_tmpl,
                                             'OS::Neutron::SecurityGroup')
        cls._collected_resources[secgroup_id] = sg_res
        cls._collected_dependencies[secgroup_id] = sg_dep
        secgroup_res.append(sg_res)
    return secgroup_res


class NetworkResourceTestCase(test.TestCase):

    def setUp(self):
        super(NetworkResourceTestCase, self).setUp()
        self.context = context.RequestContext(
            fake_object.fake_user_id,
            fake_object.fake_project_id,
            is_admin=False)
        self.net_resource = networks.NetworkResource(self.context)

    @mock.patch.object(neutron.API, 'network_list')
    def test_extract_all_nets(self, mock_net_list):
        fake_net = copy.deepcopy(fake_net_dict)
        fake_net_id = fake_net['id']
        mock_net_list.return_value = [fake_net]
        result = self.net_resource.extract_nets([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_net_id, result[0].id)
        net_dep = self.net_resource.get_collected_dependencies()[fake_net_id]
        self.assertFalse(net_dep.dependencies)

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

        fake_net_res = resource.Resource('network_0',
                                         'OS::Neutron::Net',
                                         fake_net_id)
        fake_net_dep = resource.ResourceDependency(fake_net_id,
                                                   fake_net_name,
                                                   'network_0',
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
        fake_net_id = fake_net['id']
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        fake_subnet_id = fake_subnet['id']
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_nets([fake_net_id],
                                                with_subnets=True)
        self.assertTrue(1 == len(result))
        self.assertTrue(2 == len(self.net_resource.get_collected_resources()))
        net_res = self.net_resource.get_collected_resources()[fake_net_id]
        net_dep = self.net_resource.get_collected_dependencies()[fake_net_id]
        sn_dep = self.net_resource.get_collected_dependencies()[fake_subnet_id]
        self.assertFalse(len(net_dep.dependencies))
        self.assertEqual(1, len(sn_dep.dependencies))
        self.assertIn(net_res.name, sn_dep.dependencies)

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
        collected_res = self.net_resource.get_collected_resources()
        collected_deps = self.net_resource.get_collected_dependencies()
        self.assertTrue(2 == len(collected_res))
        net_dep = collected_deps[fake_net_dict['id']]
        subnet_dep = collected_deps[fake_subnet['id']]
        self.assertFalse(len(net_dep.dependencies))
        self.assertEqual(1, len(subnet_dep.dependencies))
        self.assertIn(net_dep.name_in_template, subnet_dep.dependencies)

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
        collected_res = self.net_resource.get_collected_resources()
        collected_deps = self.net_resource.get_collected_dependencies()
        self.assertTrue(1 == len(collected_res))
        self.assertTrue(1 == len(collected_deps))
        subnet_dep = collected_deps[fake_subnet_id]
        self.assertFalse(len(subnet_dep.dependencies))

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

    @mock.patch.object(secgroup.SecGroup, 'extract_secgroups',
                       mock_extract_secgroups)
    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_with_secgroups(self, mock_port):
        # NOTE: this test will open the switch case
        # `if port.get('security_groups')`
        fake_port = copy.deepcopy(fake_port_dict)
        fake_port['security_groups'] = ['164c7126-ee4e-44e8-afb5-cc2f11225b30']
        fake_port['fixed_ips'] = []
        mock_port.return_value = fake_port
        result = self.net_resource.extract_ports([fake_port['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_port['id'], result[0].id)

    @mock.patch.object(neutron.API, 'get_port')
    def test_extract_ports_with_invalid_ips(self, mock_port):
        fake_port = copy.deepcopy(fake_port_dict)
        fake_port['fixed_ips'] = [{}]
        mock_port.return_value = fake_port
        self.assertRaises(exception.ResourceAttributesException,
                          self.net_resource.extract_ports,
                          [fake_port['id']])

    @mock.patch.object(secgroup.SecGroup, 'extract_secgroups',
                       mock_extract_secgroups)
    def test_extract_secgroups(self):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        result = self.net_resource.extract_secgroups([fake_secgroup['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_secgroup['id'], result[0].id)

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

    @mock.patch.object(neutron.API, 'get_router')
    @mock.patch.object(neutron.API, 'get_subnet', mock_new_subnet)
    @mock.patch.object(neutron.API, 'get_network', mock_new_net)
    @mock.patch.object(neutron.API, 'get_floatingip')
    def test_extract_fips_with_router(self, mock_fip, mock_router):
        # -------------------------------------------------------
        # | subnet_0(ext-sb)                    subnet_1(pri-sb)|
        # |     |                                 |             |
        # |     |                                 |             |
        # |  net_0(ext-net)<---fip     router--->net_1(pri-net) |
        # -------------------------------------------------------
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_network_id'] = ext_net_id
        fake_fip['router_id'] = fake_route_dict['id']
        mock_fip.return_value = fake_fip

        fake_router = copy.deepcopy(fake_route_dict)
        mock_router.return_value = fake_router

        result = self.net_resource.extract_floatingips([fake_fip['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_fip['id'], result[0].id)
        self.assertEqual(6, len(self.net_resource.get_collected_resources()))
        deps = self.net_resource.get_collected_dependencies()
        self.assertEqual(6, len(deps))
        fip_dep = deps.get(fake_fip['id'])
        self.assertEqual(1, len(fip_dep.dependencies))
        router_dep = deps.get(fake_fip['router_id'])
        self.assertEqual(1, len(router_dep.dependencies))

    @mock.patch.object(neutron.API, 'get_port')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'get_floatingip')
    def test_extract_fips_with_port(self, mock_fip, mock_net, mock_port):
        # NOTE: without router; with secgroup, router interface
        # Here, we will make net_0 and port_0 in cache and without any
        # dependencies, so only net_0, fip, fipAss, port_0 will be extracted
        # at last.
        # ----------------------------------------------------
        # |                                       net_1      |
        # |                                      /    |      |
        # | subnet_0(ext-sb)                    /   subnet_1 |
        # |     |                               \     |      |
        # |     |                                \    |      |
        # |  net_0(ext-net)<---fip<----fipAss--->port_0      |
        # ----------------------------------------------------
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_network_id'] = ext_net_id
        fake_fip['port_id'] = fake_port_dict['id']
        mock_fip.return_value = fake_fip
        fake_port = copy.deepcopy(fake_port_dict)
        mock_port.return_value = fake_port
        fake_port_id = fake_port['id']
        fake_port_name = fake_port['name']
        fake_port_res = resource.Resource('port_0',
                                          'OS::Neutron::Port',
                                          fake_port_id)
        fake_port_dep = resource.ResourceDependency(fake_port_id,
                                                    fake_port_name,
                                                    'port_0',
                                                    'OS::Neutron::Port')
        fake_net = copy.deepcopy(fake_net_dict)
        fake_net['id'] = fake_fip['floating_network_id']
        fake_net_id = fake_net['id']
        mock_net.return_value = fake_net
        fake_net_res = resource.Resource('net_0',
                                         'OS::Neutron::Net',
                                         fake_net_id)
        fake_net_dep = resource.ResourceDependency(fake_net_id,
                                                   fake_net_dict['name'],
                                                   'net_0',
                                                   'OS::Neutron::Net')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={
                fake_port_id: fake_port_res,
                fake_net_id: fake_net_res
            },
            collected_dependencies={
                fake_port_id: fake_port_dep,
                fake_net_id: fake_net_dep
            }
        )
        result = self.net_resource.extract_floatingips([fake_fip['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(4, len(self.net_resource.get_collected_resources()))
        deps = self.net_resource.get_collected_dependencies()
        net_dep = deps.pop(fake_net_id)
        fip_dep = deps.pop(fake_fip['id'])
        port_dep = deps.pop(fake_port_id)
        fip_ass_dep = deps.values()[0]
        self.assertIn(net_dep.name_in_template, fip_dep.dependencies)
        self.assertIn(fip_dep.name_in_template, fip_ass_dep.dependencies)
        self.assertIn(port_dep.name_in_template, fip_ass_dep.dependencies)

    @mock.patch.object(neutron.API, 'get_router')
    @mock.patch.object(neutron.API, 'get_port')
    @mock.patch.object(neutron.API, 'get_subnet', mock_new_subnet)
    @mock.patch.object(neutron.API, 'get_network', mock_new_net)
    @mock.patch.object(neutron.API, 'get_floatingip')
    def test_extract_fips_with_port_and_router(self, mock_fip, mock_port,
                                               mock_router):
        # NOTE: without router
        # ------------------------------------------------------
        # |                              router-->net_1        |
        # |                                       /   |        |
        # | subnet_0(ext-sb)                     /    subnet_1 |
        # |     |                                \    |        |
        # |     |                                 \   |        |
        # |  net_0(ext-net)<---fip<----fipAss--->port_0        |
        # ------------------------------------------------------
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_network_id'] = ext_net_id
        fake_fip['port_id'] = fake_port_dict['id']
        fake_fip['router_id'] = fake_route_dict['id']
        mock_fip.return_value = fake_fip

        fake_router = copy.deepcopy(fake_route_dict)
        mock_router.return_value = fake_router

        fake_port = copy.deepcopy(fake_port_dict)
        mock_port.return_value = fake_port

        result = self.net_resource.extract_floatingips([fake_fip['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(8, len(self.net_resource.get_collected_resources()))

        deps = self.net_resource.get_collected_dependencies()
        fip_dep = deps.pop(fake_fip['id'])
        net0_dep = deps.pop(fake_fip['floating_network_id'])
        subnet0_dep = deps.pop(ext_subnet_id)
        router_dep = deps.pop(fake_router['id'])
        net1_dep = deps.pop(fake_router['external_gateway_info']['network_id'])
        subnet1_dep = deps.pop(fake_net_dict['subnets'][0])
        port0_dep = deps.pop(fake_port['id'])
        fipass_dep = deps.values()[0]

        self.assertEqual(0, len(net0_dep.dependencies))
        self.assertEqual(0, len(net1_dep.dependencies))
        self.assertIn(net0_dep.name_in_template, subnet0_dep.dependencies)
        self.assertIn(net0_dep.name_in_template, fip_dep.dependencies)
        self.assertEqual(2, len(fipass_dep.dependencies))
        self.assertIn(fip_dep.name_in_template, fipass_dep.dependencies)
        self.assertIn(port0_dep.name_in_template, fipass_dep.dependencies)
        self.assertEqual(1, len(router_dep.dependencies))
        self.assertIn(net1_dep.name_in_template, router_dep.dependencies)
        self.assertIn(net1_dep.name_in_template, subnet1_dep.dependencies)
        self.assertEqual(2, len(port0_dep.dependencies))
        self.assertIn(net1_dep.name_in_template, port0_dep.dependencies)
        self.assertIn(subnet1_dep.name_in_template, port0_dep.dependencies)

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'router_list')
    def test_extract_all_routers(self, mock_router_list,
                                 mock_net, mock_subnet):
        fake_router = copy.deepcopy(fake_route_dict)
        mock_router_list.return_value = [fake_router]
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_routers([])
        self.assertTrue(1 == len(result))
        self.assertTrue(3 == len(self.net_resource.get_collected_resources()))
        fake_router_id = fake_router['id']
        deps = self.net_resource\
            .get_collected_dependencies()[fake_router_id].dependencies
        self.assertTrue(1 == len(deps))
        self.assertEqual('network_0', deps[0])

    @mock.patch.object(neutron.API, 'get_subnet')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(neutron.API, 'get_router')
    def test_extract_routers_with_ids(self, mock_router,
                                      mock_net, mock_subnet):
        fake_router = copy.deepcopy(fake_route_dict)
        mock_router.return_value = fake_router
        fake_net = copy.deepcopy(fake_net_dict)
        mock_net.return_value = fake_net
        fake_subnet = copy.deepcopy(fake_subnet_dict)
        mock_subnet.return_value = fake_subnet
        result = self.net_resource.extract_routers([fake_router['id']])
        self.assertTrue(1 == len(result))
        self.assertTrue(3 == len(self.net_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_router', side_effect=Exception)
    def test_extract_rotuers_failed(self, mock_router):
        self.assertRaises(exception.ResourceNotFound,
                          self.net_resource.extract_routers,
                          [fake_route_dict['id']])

    @mock.patch.object(neutron.API, 'router_list')
    def test_extract_routers_from_cache(self, mock_router_list):
        fake_router = copy.deepcopy(fake_route_dict)
        mock_router_list.return_value = [fake_router]
        fake_router_id = fake_router['id']
        fake_router_name = fake_router['name']
        fake_router_res = resource.Resource(fake_router_name,
                                            'OS::Neutron::Router',
                                            fake_router_id)

        fake_router_dep = resource.ResourceDependency(
            fake_router_id, fake_router_name, 'router_0',
            'OS::Neutron::Router')
        self.net_resource = networks.NetworkResource(
            self.context,
            collected_resources={fake_router_id: fake_router_res},
            collected_dependencies={fake_router_id: fake_router_dep})
        result = self.net_resource.extract_routers([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_router_id, result[0].id)
        self.assertTrue(1 == len(self.net_resource.get_collected_resources()))
        self.assertFalse(len(self.net_resource.get_collected_dependencies()
                             [fake_router_id].dependencies))

    @mock.patch.object(neutron.API, 'get_router')
    @mock.patch.object(neutron.API, 'port_list')
    @mock.patch.object(neutron.API, 'get_subnet', mock_new_subnet)
    @mock.patch.object(neutron.API, 'get_network', mock_new_net)
    def test_extract_network_resource(self, mock_port_list, mock_router):
        # structure chart
        # -------------------------------------------------
        # |   net_0                             subnet_1  |
        # |     |                                 |       |
        # |     |                                 |       |
        # | subnet_0 <---router_if---->router--->net_1    |
        # -------------------------------------------------
        # 1. extract net: returned from mock_new_net
        # fake_net = copy.deepcopy(fake_net_dict)
        # mock_net.return_value = fake_net
        # 2. extract subnet for net: returned from mock_new_subnet
        # fake_subnet = copy.deepcopy(fake_subnet_dict)
        # mock_subnet.return_value = fake_subnet
        # 3. extract interface: 'network:router_interface'
        fake_port = copy.deepcopy(fake_port_dict)
        if_id = fake_port['id']
        # device_id for connecting to router
        fake_port['device_id'] = fake_route_dict['id']
        fake_port['fixed_ips'][0]['subnet_id'] = sb_of_net_0_id
        fake_port['network_id'] = net_0_id
        mock_port_list.return_value = [fake_port]
        # 3.1 extract router interface
        fake_router = copy.deepcopy(fake_route_dict)
        # network_id for associating with other net
        fake_router['external_gateway_info']['network_id'] = other_net_id
        mock_router.return_value = fake_router
        # 3.2 generate interface: do not need interact with any other service,
        # only construct Res and ResDep in conveyor resource side.

        other_net_ids = [other_net_id]
        self.net_resource.extract_network_resource(net_0_id, other_net_ids)
        res = self.net_resource.get_collected_resources()
        deps = self.net_resource.get_collected_dependencies()
        self.assertEqual(6, len(res))
        self.assertEqual(6, len(deps))
        # Check deps
        net_0_dep = deps.get(net_0_id)
        net_0_sb_dep = deps.get(sb_of_net_0_id)
        other_net_dep = deps.get(other_net_id)
        other_net_sb_dep = deps.get(sb_of_other_net_id)
        if_dep = deps.get(if_id)
        router_dep = deps.get(fake_router['id'])
        self.assertEqual(0, len(net_0_dep.dependencies))
        self.assertEqual(0, len(other_net_dep.dependencies))
        self.assertIn(net_0_dep.name_in_template, net_0_sb_dep.dependencies)
        self.assertIn(other_net_dep.name_in_template,
                      other_net_sb_dep.dependencies)
        self.assertIn(other_net_dep.name_in_template,
                      router_dep.dependencies)
        self.assertIn(router_dep.name_in_template, if_dep.dependencies)
        self.assertIn(net_0_sb_dep.name_in_template, if_dep.dependencies)
        self.assertEqual(2, len(if_dep.dependencies))

    @mock.patch.object(neutron.API, 'get_router')
    @mock.patch.object(neutron.API, 'port_list')
    @mock.patch.object(neutron.API, 'get_subnet', mock_new_subnet)
    @mock.patch.object(neutron.API, 'get_network', mock_new_net)
    def test_extract_networks_resource(self, mock_port_list, mock_router):
        fake_port = copy.deepcopy(fake_port_dict)
        if_id = fake_port['id']
        fake_port['device_id'] = fake_route_dict['id']
        fake_port['fixed_ips'][0]['subnet_id'] = sb_of_net_0_id
        fake_port['network_id'] = net_0_id
        mock_port_list.return_value = [fake_port]

        fake_router = copy.deepcopy(fake_route_dict)
        fake_router['external_gateway_info']['network_id'] = other_net_id
        mock_router.return_value = fake_router

        self.net_resource.extract_networks_resource([net_0_id, other_net_id])

        res = self.net_resource.get_collected_resources()
        deps = self.net_resource.get_collected_dependencies()
        self.assertEqual(6, len(res))
        self.assertEqual(6, len(deps))
        # Check deps
        net_0_dep = deps.get(net_0_id)
        net_0_sb_dep = deps.get(sb_of_net_0_id)
        other_net_dep = deps.get(other_net_id)
        other_net_sb_dep = deps.get(sb_of_other_net_id)
        if_dep = deps.get(if_id)
        router_dep = deps.get(fake_router['id'])
        self.assertEqual(0, len(net_0_dep.dependencies))
        self.assertEqual(0, len(other_net_dep.dependencies))
        self.assertIn(net_0_dep.name_in_template, net_0_sb_dep.dependencies)
        self.assertIn(other_net_dep.name_in_template,
                      other_net_sb_dep.dependencies)
        self.assertIn(other_net_dep.name_in_template,
                      router_dep.dependencies)
        self.assertIn(router_dep.name_in_template, if_dep.dependencies)
        self.assertIn(net_0_sb_dep.name_in_template, if_dep.dependencies)
        self.assertEqual(2, len(if_dep.dependencies))
