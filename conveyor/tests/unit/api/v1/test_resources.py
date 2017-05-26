# Copyright 2011 OpenStack Foundation
# Copyright 2011 Justin Santa Barbara
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

import mock
from webob import exc

from conveyor.api import extensions
from conveyor.api.v1 import resources
from conveyor import context
from conveyor.resource import api as resource_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes

from conveyor.tests.unit import fake_constants as fake


class ResourceControllerTestCase(test.TestCase):

    def setUp(self):
        super(ResourceControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)
        self.ext_mgr = extensions.ExtensionManager()
        self.ext_mgr.extensions = {}
        self.controller = resources.Controller(self.ext_mgr)

    @mock.patch.object(resource_api.ResourceAPI, 'get_resource_types')
    def test_resource_types(self, mock_get_resource_types):
        plan_id = fake.PLAN_ID
        res_types = ['OS:Nova:Server']
        req = fakes.HTTPRequest.blank('/v1/resources/%s' + plan_id)
        mock_get_resource_types.return_value = res_types
        rsp = self.controller.types(req)
        self.assertEqual(res_types[0], rsp['types'][0]['type'])

    @mock.patch.object(resource_api.ResourceAPI, 'get_resources')
    def test_resource_detail(self, mock_get_resources):
        resources = [{
            "name": "stack_0",
            "parameters": {},
            "id": "e76f3947-d76f-4dca-a5f4-5af9b57becfe",
            "type": "OS::Heat::Stack",
            "properties": {
                "stack_name": "test-stack",
                "disable_rollback": True,
                "parameters": {
                    "OS::project_id": "d23b65e027f9461ebe900916c0412ade",
                    "image": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                    "flavor": "2",
                    "OS::stack_name": "test-stack"}}}]
        req = fakes.HTTPRequest.blank('/v1/resources')
        req.GET['type'] = 'fake-test'
        mock_get_resources.return_value = resources
        rsp = self.controller.detail(req)
        self.assertEqual(resources[0]['id'], rsp['resources'][0]['id'])

    @mock.patch.object(resource_api.ResourceAPI, 'get_resources')
    def test_resource_detail_failed_no_type(self, mock_get_resources):
        resources = [{
            "name": "stack_0",
            "parameters": {},
            "id": "e76f3947-d76f-4dca-a5f4-5af9b57becfe",
            "type": "OS::Heat::Stack",
            "properties": {
                "stack_name": "test-stack",
                "disable_rollback": True,
                "parameters": {
                    "OS::project_id": "d23b65e027f9461ebe900916c0412ade",
                    "image": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                    "flavor": "2",
                    "OS::stack_name": "test-stack"}}}]
        req = fakes.HTTPRequest.blank('/v1/resources')
        mock_get_resources.return_value = resources
        self.assertRaises(exc.HTTPBadRequest, self.controller.detail,
                          req)
