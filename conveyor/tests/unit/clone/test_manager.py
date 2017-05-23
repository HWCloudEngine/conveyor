#    Copyright 2016 Red Hat, Inc.
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

from conveyor.clone import manager
from conveyor.resource import api as resource_api

from conveyor import context
from conveyor import exception


class CloneManagerTestCase(testtools.TestCase):

    def setUp(self):
        super(CloneManagerTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.clone_manager = manager.CloneManager()

    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_export_clone_template(self, get_plan_by_id_mock):
        get_plan_by_id_mock.return_value = None
        fake_id = 'fake-001'
        sys_clone = False
        self.assertRaises(exception.PlanNotFound,
                          self.clone_manager.export_clone_template,
                          self.context, fake_id, sys_clone)
