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
from conveyor.heat import heat
from conveyor.resource.driver import stacks
from conveyor.resource import resource
from conveyor.tests import test

fake_stack_dict = {
    "disable_rollback": True,
    "description": "A recorded server",
    "parent": None,
    "tags": None,
    "stack_name": "test-stack",
    "stack_user_project_id": "ac820807a4c8474793ee872c048dc7c6",
    "stack_status_reason": "Stack CREATE completed successfully",
    "creation_time": "2017-05-20T09:22:12.672734",
    "capabilities": [],
    "notification_topics": [],
    "updated_time": None,
    "timeout_mins": None,
    "stack_status": "CREATE_COMPLETE",
    "stack_owner": None,
    "parameters": {
        "OS::project_id": "d23b65e027f9461ebe900916c0412ade",
        "OS::stack_id": "e76f3947-d76f-4dca-a5f4-5af9b57becfe",
        "OS::stack_name": "test-stack",
        "image": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
        "private_network_id": "01329398-2050-4152-a034-c1b302e70619",
        "flavor": "2"
    },
    "id": "e76f3947-d76f-4dca-a5f4-5af9b57becfe",
    "outputs": [],
    "template_description": "A recorded server"
}

fake_stack_tmpl_dict = {
    "heat_template_version": "2013-05-23",
    "description": "A recorded server",
    "parameters": {
        "image": {
            "default": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
            "type": "string"
        },
        "private_network_id": {
            "default": "01329398-2050-4152-a034-c1b302e70619",
            "type": "string"
        },
        "flavor": {
            "default": 2,
            "type": "string"
        }
    },
    "resources": {
        "server": {
            "type": "OS::Nova::Server",
            "properties": {
                "flavor": {
                    "get_param": "flavor"
                },
                "networks": [
                    {
                        "network": {
                            "get_param": "private_network_id"
                        }
                    }
                ],
                "image": {
                    "get_param": "image"
                },
                "availability_zone": "az01.dc1--fusionsphere"
            }
        }
    }
}

fake_stack_resoures = [
    {
        "resource_name": "server",
        "logical_resource_id": "server",
        "creation_time": "2017-05-20T09:22:13.540363",
        "resource_status": "CREATE_COMPLETE",
        "updated_time": "2017-05-20T09:22:13.540363",
        "required_by": [],
        "resource_status_reason": "state changed",
        "physical_resource_id": "3e1aff22-f32e-40b8-b33f-a0be6d2955cc",
        "resource_type": "OS::Nova::Server"
    }
]


class StackResourceTesetCase(test.TestCase):
    def setUp(self):
        super(StackResourceTesetCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.stack_resource = stacks.StackResource(self.context)

    @mock.patch.object(heat.API, 'resources_list')
    @mock.patch.object(heat.API, 'get_template')
    @mock.patch.object(heat.API, 'stack_list')
    def test_extract_all_stacks(self, mock_stack_list, mock_stack_tmpl,
                                mock_stack_res):
        fake_stack = copy.deepcopy(fake_stack_dict)
        mock_stack_list.return_value = [fake_stack]
        fake_tmpl = copy.deepcopy(fake_stack_tmpl_dict)
        mock_stack_tmpl.return_value = fake_tmpl
        fake_res = copy.deepcopy(fake_stack_resoures)
        mock_stack_res.return_value = fake_res

        result = self.stack_resource.extract_stacks([])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_stack['id'], result[0].id)

    @mock.patch.object(heat.API, 'resources_list')
    @mock.patch.object(heat.API, 'get_template')
    @mock.patch.object(heat.API, 'get_stack')
    def test_extract_stacks_with_ids(self, mock_stack, mock_stack_tmpl,
                                mock_stack_res):
        fake_stack = copy.deepcopy(fake_stack_dict)
        mock_stack.return_value = fake_stack
        fake_tmpl = copy.deepcopy(fake_stack_tmpl_dict)
        mock_stack_tmpl.return_value = fake_tmpl
        fake_res = copy.deepcopy(fake_stack_resoures)
        mock_stack_res.return_value = fake_res

        result = self.stack_resource.extract_stacks([fake_stack['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_stack['id'], result[0].id)

    @mock.patch.object(heat.API, 'get_stack', side_effect=Exception)
    def test_extract_stacks_failed(self, mock_stack):
        self.assertRaises(exception.ResourceNotFound,
                          self.stack_resource.extract_stacks,
                          [fake_stack_dict['id']])
        fake_stack = copy.deepcopy(fake_stack_dict)
        mock_stack.return_value = fake_stack

    @mock.patch.object(heat.API, 'get_stack')
    def test_extract_stacks_from_cache(self, mock_stack):
        fake_stack = copy.deepcopy(fake_stack_dict)
        mock_stack.return_value = fake_stack

        fake_stack_res = resource.Resource('stack_0',
                                           'OS::Heat::Stack',
                                           fake_stack['id'])
        fake_stack_dep = resource.ResourceDependency(fake_stack['id'],
                                                     fake_stack['stack_name'],
                                                     'stack_0',
                                                     'OS::Heat::Stack')

        self.stack_resource = stacks.StackResource(
            self.context,
            collected_resources={fake_stack['id']: fake_stack_res},
            collected_dependencies={fake_stack['id']: fake_stack_dep}
        )

        result = self.stack_resource.extract_stacks([fake_stack['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_stack['id'], result[0].id)
