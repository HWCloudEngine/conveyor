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
import testtools
import webob

from six.moves import http_client

from oslo_log import log as logging
from oslo_serialization import jsonutils

from conveyor.clone import api
from conveyor.tests.unit.api import fakes as fakes
from conveyor.tests.unit import fake_constants as fake

from conveyor import context

LOG = logging.getLogger(__name__)


class CloneActionControllerTestCase(testtools.TestCase):

    def setUp(self):
        super(CloneActionControllerTestCase, self).setUp()
        self.context = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                              is_admin=False)

    @mock.patch.object(api.API, "start_template_clone")
    def test_start_template_clone(self, start_template_clone_mock):
        start_template_clone_mock.return_value = {}
        expire_time = '2030-01-01 08:38:01.567226'
        body = {'clone_element_template': {'template':
                                           {'expire_time': expire_time,
                                            'plan_type': 'clone'}
                                           }}
        req = webob.Request.blank('/v1/%s/clones/%s/action' %
                                  (fake.PROJECT_ID, fake.PLAN_ID))
        req.method = "POST"
        req.body = jsonutils.dump_as_bytes(body)
        req.headers["content-type"] = "application/json"

        res = req.get_response(fakes.wsgi_app(fake_auth_context=self.context))
        self.assertEqual(http_client.OK, res.status_int)
