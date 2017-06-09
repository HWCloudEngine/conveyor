# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

import datetime
import iso8601
import mock
from webob import exc

from conveyor.api import extensions
from conveyor.api.v1 import plans
from conveyor import context
from conveyor import exception
from conveyor.plan import api as plan_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit.api.v1 import fakes as res_fakes
from conveyor.tests.unit import fake_constants as fake


class PlanControllerTestCase(test.TestCase):

    def setUp(self):
        super(PlanControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)
        self.ext_mgr = extensions.ExtensionManager()
        self.ext_mgr.extensions = {}
        self.controller = plans.Controller(self.ext_mgr)

    def _expected_plan_from_controller(self, plan_id, plan_type='clone',
                                       resources='', update_resources=''):
        plan = {
            'id': plan_id,
            'user_id': fake.USER_ID,
            'project_id': fake.PROJECT_ID,
            'availability_zone': res_fakes.DEFAULT_AZ,
            'plan_status': res_fakes.DEFAULT_PLAN_STATUS,
            'expire_at': datetime.datetime(2020, 1, 1, 1, 1, 1,
                                           tzinfo=iso8601.iso8601.Utc()),
            'name': 'plan_test',
            'display_name': res_fakes.DEFAULT_PLAN_NAME,
            'display_description': res_fakes.DEFAULT_PLAN_DESCRIPTION,
            'updated_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                            tzinfo=iso8601.iso8601.Utc()),
            'created_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                            tzinfo=iso8601.iso8601.Utc()),
            'plan_type': plan_type,
            'original_resource': resources,
            'update_resources': update_resources
        }
        return {'plan': plan}

    def _plan_in_request_body(self, plan_id, plan_type,
                              resources, *args, **kwargs):
        plan = {
            'id': plan_id,
            'user_id': fake.USER_ID,
            'project_id': fake.PROJECT_ID,
            'availability_zone': res_fakes.DEFAULT_AZ,
            'plan_status': res_fakes.DEFAULT_PLAN_STATUS,
            'expire_at': datetime.datetime(2020, 1, 1, 1, 1, 1,
                                           tzinfo=iso8601.iso8601.Utc()),
            'name': 'plan_test',
            'display_name': res_fakes.DEFAULT_PLAN_NAME,
            'display_description': res_fakes.DEFAULT_PLAN_DESCRIPTION,
            'updated_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                            tzinfo=iso8601.iso8601.Utc()),
            'created_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                            tzinfo=iso8601.iso8601.Utc()),
            'type': plan_type,
            'resources': resources,
            'update_resources': ''
        }
        return plan

    @mock.patch.object(plan_api.PlanAPI, 'get_plan_by_id',
                       res_fakes.fake_plan_api_get)
    def test_plan_show(self):
        req = fakes.HTTPRequest.blank('/v1/plans/%s' % fake.PLAN_ID)
        res_dict = self.controller.show(req, fake.PLAN_ID)
        expected = self._expected_plan_from_controller(fake.PLAN_ID)
        self.assertEqual(expected, res_dict)

    @mock.patch.object(plan_api.PlanAPI, 'get_plan_by_id')
    def test_plan_show_no_plan(self, get_plan_mock):
        get_plan_mock.side_effect = exception.PlanNotFound(fake.PLAN_ID)
        req = fakes.HTTPRequest.blank('/v1/plans/%s' % fake.PLAN_ID)
        self.assertRaises(exc.HTTPInternalServerError, self.controller.show,
                          req, fake.PLAN_ID)

    @mock.patch.object(plan_api.PlanAPI, 'create_plan')
    def test_plan_create(self, create_plan_mock):
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
        plan = self._plan_in_request_body(fake.PLAN_ID, 'clone', resources)
        create_plan_mock.return_value = fake.PLAN_ID, plan
        body = {"plan": plan}
        req = fakes.HTTPRequest.blank('/v1/plans')
        res_dict = self.controller.create(req, body)
        ex = self._expected_plan_from_controller(fake.PLAN_ID, resources)
        self.assertEqual(ex['plan']['id'], res_dict['plan']['plan_id'])

    def test_plan_create_fails_with_invdlid_type(self):
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
        plan = self._plan_in_request_body(fake.PLAN_ID, '', resources)
        body = {'plan': plan}
        req = fakes.HTTPRequest.blank('/v1/plans/')
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          req, body)

    def test_plan_create_fails_with_invdlid_resource(self):
        resources = [{
            "name": "stack_0",
            "parameters": {},
            "id": "e76f3947-d76f-4dca-a5f4-5af9b57becfe",
            "type": "OS::Heat::AAAAA",
            "properties": {
                "stack_name": "test-stack",
                "disable_rollback": True,
                "parameters": {
                    "OS::project_id": "d23b65e027f9461ebe900916c0412ade",
                    "image": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                    "flavor": "2",
                    "OS::stack_name": "test-stack"}}}]
        plan = self._plan_in_request_body(fake.PLAN_ID, 'clone', resources)
        body = {'plan': plan}
        req = fakes.HTTPRequest.blank('/v1/plans/')
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          req, body)

    def test_plan_create_fails_with_no_resource(self):
        plan = self._plan_in_request_body(fake.PLAN_ID, 'clone', '')
        body = {'plan': plan}
        req = fakes.HTTPRequest.blank('/v1/plans/')
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          req, body)

    @mock.patch.object(plan_api.PlanAPI, 'create_plan_by_template')
    def test_create_plan_by_template(self, mock_create_plan_by_template):
        template = res_fakes.fake_clone_template()
        body = {'plan': template}
        req = fakes.HTTPRequest.blank('/v1/plans/')
        mock_create_plan_by_template.return_value = template
        plan_dict = self.controller.create_plan_by_template(req, body)
        self.assertEqual(template, plan_dict['plan'])

    @mock.patch.object(plan_api.PlanAPI,
                       'delete_plan', return_value=None)
    def test_plan_delete(self, mock_delete_plan):
        plan_id = fake.PLAN_ID
        req = fakes.HTTPRequest.blank('/v1/plans/%s' + plan_id)
        ctx = req.environ['conveyor.context']
        self.controller.delete(req, plan_id)
        mock_delete_plan.assert_called_once_with(ctx, plan_id)

    @mock.patch.object(plan_api.PlanAPI,
                       'update_plan', return_value=None)
    def test_update_pan(self, mock_update_plan):
        plan_id = fake.PLAN_ID
        update_resource = {'name': 'fake-test'}
        body = {'plan': update_resource}
        req = fakes.HTTPRequest.blank('/v1/plans/%s' + plan_id)
        ctx = req.environ['conveyor.context']
        self.controller.update(req, plan_id, body)
        mock_update_plan.assert_called_once_with(ctx, plan_id,
                                                 update_resource)

    @mock.patch.object(plan_api.PlanAPI,
                       'update_plan_resources', return_value=None)
    def test_update_plan_resources(self, mock_update_plan_resources):
        plan_id = fake.PLAN_ID
        update_resource = {'resources': {'name': 'fake-test'}}
        body = {'update_plan_resources': update_resource}
        req = fakes.HTTPRequest.blank('/v1/plans/%s' + plan_id)
        ctx = req.environ['conveyor.context']
        self.controller._update_plan_resources(req, plan_id, body)
        mock_update_plan_resources.assert_called_once_with(
                                        ctx, plan_id,
                                        update_resource.get('resources'))

    @mock.patch.object(plan_api.PlanAPI, 'get_plans')
    def test_plan_detail(self, mock_get_plans):
        req = fakes.HTTPRequest.blank('/v1/plans')
        plan = res_fakes.create_fake_plan(fake.PLAN_ID)
        mock_get_plans.return_value = [plan]
        res_dict = self.controller.detail(req)
        self.assertEqual(res_dict['plans'][0]['id'], fake.PLAN_ID)
