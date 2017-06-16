# Copyright 2011 OpenStack Foundation
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


import mock
import webob

from six.moves import http_client

from oslo_log import log as logging
from oslo_serialization import jsonutils

from conveyor.clone import api
from conveyor import context
from conveyor.plan import api as plan_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit.api.v1 import fakes as res_fakes
from conveyor.tests.unit import fake_constants as fake


LOG = logging.getLogger(__name__)


class CloneActionControllerTestCase(test.TestCase):

    def setUp(self):
        super(CloneActionControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)

    @mock.patch.object(api.API, "start_template_clone")
    def test_start_template_clone(self, start_template_clone_mock):
        start_template_clone_mock.return_value = {}
        body = {'clone_element_template': {'template':
                                           {'plan_type': 'clone'}
                                           }}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(api.API, "export_clone_template")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_export_clone_template(self, mock_get_plan_by_id,
                                   mock_export_clone_template):
        body = {'export_clone_template': {'sys_clone': False}}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        fake_plan = res_fakes.create_fake_plan(plan_id,
                                               plan_status='creating')
        mock_get_plan_by_id.return_value = fake_plan
        mock_export_clone_template.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(api.API, "export_clone_template")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_export_clone_template_invalid_status(self, mock_get_plan_by_id,
                                                  mock_export_clone_template):
        body = {'export_clone_template': {'sys_clone': False}}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        fake_plan = res_fakes.create_fake_plan(plan_id,
                                               plan_status='cloning')
        mock_get_plan_by_id.return_value = fake_plan
        mock_export_clone_template.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.BAD_REQUEST, res.status_int)

    @mock.patch.object(api.API, "clone")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_clone(self, mock_get_plan_by_id, mock_clone):
        body = {'clone': {'sys_clone': False,
                          'destination': 'fake-az'}}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        mock_get_plan_by_id.return_value = res_fakes.create_fake_plan(plan_id)
        mock_clone.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(api.API, "clone")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_clone_invalid_status(self, mock_get_plan_by_id, mock_clone):
        body = {'clone': {'sys_clone': False,
                          'destination': 'fake-az'}}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        fake_plan = res_fakes.create_fake_plan(plan_id,
                                               plan_status='error')
        mock_get_plan_by_id.return_value = fake_plan
        mock_clone.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.BAD_REQUEST, res.status_int)

    @mock.patch.object(api.API, "export_template_and_clone")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_export_template_and_clone(self, mock_get_plan_by_id,
                                       mock_export_template_and_clone):
        body = {'export_template_and_clone': {'sys_clone': False,
                                              'destination': 'fake-az',
                                              'resources': {}}}

        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        fake_plan = res_fakes.create_fake_plan(plan_id,
                                               plan_status='creating')
        mock_get_plan_by_id.return_value = fake_plan
        mock_export_template_and_clone.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(api.API, "export_template_and_clone")
    @mock.patch.object(plan_api.PlanAPI, "get_plan_by_id")
    def test_export_template_and_clone_invalid_status(
                                        self, mock_get_plan_by_id,
                                        mock_export_template_and_clone):
        body = {'export_template_and_clone': {'sys_clone': False,
                                              'destination': 'fake-az',
                                              'resources': {}}}

        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        fake_plan = res_fakes.create_fake_plan(plan_id,
                                               plan_status='cloning')
        mock_get_plan_by_id.return_value = fake_plan
        mock_export_template_and_clone.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.BAD_REQUEST, res.status_int)
