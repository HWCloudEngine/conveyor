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
from conveyor.resource.driver import secgroup
from conveyor.resource import resource
from conveyor.tests import test

fake_user_id = '01329398-2050-4152-a034-c1b302e70619'
fake_project_id = '0e7eb10bac1a4055a0381f0ae36c9e98'

fake_secgroup_dict = {
      "tenant_id": "0e7eb10bac1a4055a0381f0ae36c9e98",
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
          "tenant_id": "0e7eb10bac1a4055a0381f0ae36c9e98",
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
          "tenant_id": "0e7eb10bac1a4055a0381f0ae36c9e98",
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
          "tenant_id": "0e7eb10bac1a4055a0381f0ae36c9e98",
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
          "tenant_id": "0e7eb10bac1a4055a0381f0ae36c9e98",
          "port_range_min": None,
          "ethertype": "IPv6"
        }
      ],
      "name": "default"
    }


class SecGroupTestCase(test.TestCase):

    def setUp(self):
        super(SecGroupTestCase, self).setUp()
        self.context = context.RequestContext(fake_user_id, fake_project_id,
                                              is_admin=False)
        self.secgroup_resource = secgroup.SecGroup(self.context)

    @mock.patch.object(neutron.API, 'secgroup_list')
    def test_extract_all_secgroups(self, mock_secgroup_list):
        # NOTE: does secgroup.SecGroup contain method _tenant_filter ?
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup_list.return_value = [fake_secgroup]
        result = self.secgroup_resource.extract_secgroups([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_secgroup['id'], result[0].id)
        self.assertTrue(
            1 == len(self.secgroup_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'get_security_group')
    def test_extract_secgroups_with_ids(self, mock_secgroup):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup.return_value = fake_secgroup
        fake_sg_id = fake_secgroup['id']
        result = self.secgroup_resource.extract_secgroups([fake_sg_id])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_sg_id, result[0].id)
        self.assertTrue(
            1 == len(self.secgroup_resource.get_collected_resources()))

    @mock.patch.object(neutron.API, 'secgroup_list')
    def test_extract_secgroups_from_cache(self, mock_secgroup_list):
        fake_secgroup = copy.deepcopy(fake_secgroup_dict)
        mock_secgroup_list.return_value = [fake_secgroup]
        fake_sg_id =fake_secgroup['id']
        fake_sg_name = fake_secgroup['name']

        fake_net_res = resource.Resource(fake_sg_name,
                                         'OS::Neutron::SecurityGroup',
                                         fake_sg_id)
        fake_net_dep = resource.ResourceDependency(fake_sg_id,
                                                   fake_sg_name,
                                                   'securitygroup_0',
                                                   'OS::Neutron::SecurityGroup')
        self.secgroup_resource = secgroup.SecGroup(
            self.context,
            collected_resources={fake_sg_id: fake_net_res},
            collected_dependencies={fake_sg_id: fake_net_dep})
        result = self.secgroup_resource.extract_secgroups([])
        self.assertTrue(1 == len(result))
        self.assertEqual(fake_sg_id, result[0].id)

    @mock.patch.object(neutron.API, 'get_security_group',
                       side_effect=Exception)
    def test_extract_secgroups_failed(self, mock_secgroup):
        self.assertRaises(exception.ResourceNotFound,
                          self.secgroup_resource.extract_secgroups,
                          ['sg_123'])

    # @mock.patch.object(neutron.API, 'get_security_group')
    # def test_extract_secgroups_none(self, mock_secgroup):
    #     mock_secgroup.return_value = []
    #     self.assertRaises(
    #         exception.ResourceNotFound,
    #         self.secgroup_resource.extract_secgroups(['sg_123']))
