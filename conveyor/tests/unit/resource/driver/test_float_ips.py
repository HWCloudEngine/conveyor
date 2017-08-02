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
from conveyor.resource.driver import float_ips
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object

fake_fip_dict = fake_object.fake_fip_dict
fake_net_dict = fake_object.fake_net_dict
fake_subnet_dict = fake_object.fake_subnet_dict


class NetworkResourceTestCase(test.TestCase):

    def setUp(self):
        super(NetworkResourceTestCase, self).setUp()
        self.context = context.RequestContext(
            fake_object.fake_user_id,
            fake_object.fake_project_id,
            is_admin=False)
        self.fip_resource = float_ips.FloatIps(self.context)

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
        result = self.fip_resource.extract_floatingips([])
        self.assertTrue(1 == len(result))
        self.assertTrue(
            3 == len(self.fip_resource.get_collected_resources()))

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
        result = self.fip_resource.extract_floatingips([fake_fip['id']])
        self.assertTrue(1 == len(result))
        self.assertTrue(
            3 == len(self.fip_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_floatingip',
                       side_effect=Exception)
    def test_extract_fips_failed(self, mock_fip):
        self.assertRaises(exception.ResourceNotFound,
                          self.fip_resource.extract_floatingips,
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
                                                   'floatingip_0',
                                                   fake_fip_name,
                                                   'OS::Neutron::FloatingIP')
        self.fip_resource = float_ips.FloatIps(
            self.context,
            collected_resources={fake_fip_id: fake_fip_res},
            collected_dependencies={fake_fip_id: fake_fip_dep})
        result = self.fip_resource.extract_floatingips([])
        self.assertTrue(1 == len(result))
        self.assertTrue(
            1 == len(self.fip_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_fips_with_invalid_ip(self, mock_fip_list):
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_ip_address'] = ''
        mock_fip_list.return_value = [fake_fip]
        self.assertRaises(exception.ResourceAttributesException,
                          self.fip_resource.extract_floatingips,
                          [])

    @mock.patch.object(neutron.API, 'floatingip_list')
    def test_extract_fips_with_invalid_net(self, mock_fip_list):
        fake_fip = copy.deepcopy(fake_fip_dict)
        fake_fip['floating_network_id'] = ''
        mock_fip_list.return_value = [fake_fip]
        self.assertRaises(exception.ResourceAttributesException,
                          self.fip_resource.extract_floatingips,
                          [])
