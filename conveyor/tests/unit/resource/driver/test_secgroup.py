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
from conveyor.tests.unit.resource import fake_object

fake_secgroup_dict = fake_object.fake_secgroup_dict


class SecGroupTestCase(test.TestCase):

    def setUp(self):
        super(SecGroupTestCase, self).setUp()
        self.context = context.RequestContext(
            fake_object.fake_user_id,
            fake_object.fake_project_id,
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
        fake_sg_id = fake_secgroup['id']
        fake_sg_name = fake_secgroup['name']

        fake_net_res = resource.Resource(fake_sg_name,
                                         'OS::Neutron::SecurityGroup',
                                         fake_sg_id)
        fake_net_dep = resource.ResourceDependency(
            fake_sg_id, fake_sg_name, 'securitygroup_0',
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
