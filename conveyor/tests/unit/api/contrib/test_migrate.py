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
import webob

from six.moves import http_client

from oslo_serialization import jsonutils

from conveyor.clone import api
from conveyor import context
from conveyor.resource import api as resource_api
from conveyor.tests import test
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit.api.v1 import fakes as res_fakes
from conveyor.tests.unit import fake_constants as fake


class MigrateActionControllerTestCase(test.TestCase):

    def setUp(self):
        super(MigrateActionControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)

    @mock.patch.object(api.API, "migrate")
    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_migrate(self, mock_get_plan_by_id, mock_migrate):
        body = {'migrate': {'destination': 'fake-az'}}
        req = webob.Request.blank('/v1/%s/migrates/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        mock_get_plan_by_id.return_value = res_fakes.create_fake_plan(plan_id)
        mock_migrate.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)

    @mock.patch.object(api.API, "export_migrate_template")
    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_export_migrate_template(self, mock_get_plan_by_id,
                                     mock_export_migrate_template):
        body = {'export_migrate_template': {'destination': 'fake-az'}}
        req = webob.Request.blank('/v1/%s/migrates/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"
        plan_id = fake.PLAN_ID
        mock_get_plan_by_id.return_value = res_fakes.create_fake_plan(plan_id)
        mock_export_migrate_template.return_value = {}
        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.ACCEPTED, res.status_int)
