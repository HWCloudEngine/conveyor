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


class NetworkResourceTestCase(test.TestCase):

    def setUp(self):
        super(NetworkResourceTestCase, self).setUp()
        self.context = context.RequestContext(fake_user_id, fake_project_id,
                                              is_admin=False)
        self.net_resource = networks.NetworkResource(self.context)

    @mock.patch.object(neutron.API, 'network_list')
    def test_extract_nets(self, mock_net_list):
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
        fake_net_id =fake_net['id']
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

    def test_extract_nets_with_subnets(self):
        pass
