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

from conveyor.api.contrib import resource
from conveyor import context
from conveyor.resource import api as resource_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit import fake_constants as fake


class ResourceActionControllerTestCase(test.TestCase):

    def setUp(self):
        super(ResourceActionControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)
        self.controller = resource.ResourceActionController()

    @mock.patch.object(resource_api.ResourceAPI, 'get_resource_detail')
    def test_get_resource_detail(self, mock_get_resource_detail):
        resource = {
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
                    "OS::stack_name": "test-stack"}}}
        plan_id = fake.PLAN_ID
        req = fakes.HTTPRequest.blank('/v1/resources/%s/action' + plan_id)
        res_type = {'type': 'fake'}
        body = {'get_resource_detail': res_type}
        mock_get_resource_detail.return_value = resource
        rsp = self.controller._get_resource_detail(req, plan_id, body)
        self.assertEqual(resource['id'], rsp['resource']['id'])
