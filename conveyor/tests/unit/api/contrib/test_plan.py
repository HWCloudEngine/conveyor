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

from six.moves import http_client


from conveyor.api.contrib import plan
from conveyor.clone import api as clone_api
from conveyor import context
from conveyor.db import api as db_api
from conveyor.plan import api as plan_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit.api.v1 import fakes as res_fakes
from conveyor.tests.unit import fake_constants as fake


class PlanActionControllerTestCase(test.TestCase):

    def setUp(self):
        super(PlanActionControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)
        self.controller = plan.PlansActionController()

    @mock.patch.object(clone_api.API, 'download_template')
    @mock.patch.object(db_api, 'plan_get')
    def test_download_template(self, mock_get_plan_by_id,
                               mock_download_template):
        plan_id = fake.PLAN_ID
        body = {'download_template': {'plan_id': plan_id}}
        plan = res_fakes.create_fake_plan(plan_id)
        mock_download_template.return_value = 'fake-content'
        mock_get_plan_by_id.return_value = plan
        req = fakes.HTTPRequest.blank('/v1/plans/%s/action' + plan_id)
        rsp = self.controller._download_template(req, plan_id, body)
        self.assertEqual('fake-content', rsp)

    @mock.patch.object(plan_api.PlanAPI,
                       'update_plan', return_value=None)
    def test_reset_state(self, mock_update_plan):
        plan_id = fake.PLAN_ID
        body = {'os-reset_state': {'plan_status': 'cloning'}}
        req = fakes.HTTPRequest.blank('/v1/plans/%s/action' + plan_id)
        rsp = self.controller._reset_state(req, plan_id, body)
        self.assertEqual('cloning', rsp['plan_status'])

    @mock.patch.object(plan_api.PlanAPI,
                       'force_delete_plan', return_value=None)
    def _force_delete_plan(self, mock_force_delete_plan):
        plan_id = fake.PLAN_ID
        body = {'force_delete-plan': {'plan_id': plan_id}}
        req = fakes.HTTPRequest.blank('/v1/plans/%s/action' + plan_id)
        res = self.controller._force_delete_plan(req, plan_id, body)
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(plan_api.PlanAPI,
                       'plan_delete_resource', return_value=None)
    def test_plan_delete_resource(self, mock_plan_delete_resource):
        plan_id = fake.PLAN_ID
        body = {'plan-delete-resource': {'plan_id': plan_id}}
        req = fakes.HTTPRequest.blank('/v1/plans/%s/action' + plan_id)
        self.controller._plan_delete_resource(req, plan_id, body)
        ctx = req.environ['conveyor.context']
        mock_plan_delete_resource.assert_called_once_with(ctx, plan_id)

    @mock.patch.object(plan_api.PlanAPI,
                       'get_resource_detail_from_plan')
    def test_resource_detail(self, mock_get_resources_detail_from_plan):

        res_id = "e76f3947-d76f-4dca-a5f4-5af9b57becfe"
        resource = {
            "name": "stack_0",
            "parameters": {},
            "id": res_id,
            "type": "OS::Heat::Stack",
            "properties": {
                "stack_name": "test-stack",
                "disable_rollback": True,
                "parameters": {
                    "OS::project_id": "d23b65e027f9461ebe900916c0412ade",
                    "image": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                    "flavor": "2",
                    "OS::stack_name": "test-stack"}}}
        req = fakes.HTTPRequest.blank('/v1/plans/%s/action' + res_id)
        body = {'get_resource_detail_from_plan': {'plan_id': fake.PLAN_ID}}
        mock_get_resources_detail_from_plan.return_value = resource
        rsp = self.controller._get_resource_detail_from_plan(req, res_id, body)
        self.assertEqual(resource['id'], rsp['resource']['id'])
