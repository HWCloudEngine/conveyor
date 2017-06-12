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
from conveyor.db import api as db_api
from conveyor import exception
from conveyor.objects import plan
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object


class ResourceTestCase(test.TestCase):

    def setUp(self):
        super(ResourceTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)

    @mock.patch.object(db_api, 'plan_create')
    def test_save_plan_to_db(self, mock_plan_create):
        plan.save_plan_to_db(self.context, fake_object.fake_plan_dict)
        mock_plan_create.assert_called_once()

    @mock.patch.object(db_api, 'plan_create', side_effect=Exception)
    def test_save_plan_to_db_failed(self, mock_plan_create):
        self.assertRaises(exception.PlanCreateFailed,
                          plan.save_plan_to_db,
                          self.context,
                          fake_object.fake_plan_dict)
        mock_plan_create.assert_called_once()

    @mock.patch.object(db_api, 'plan_get')
    def test_read_plan_from_db(self, mock_plan_get):
        fake_plan = copy.deepcopy(fake_object.fake_plan_dict)
        fake_plan.pop('original_dependencies', None)
        fake_plan.pop('updated_dependencies', None)
        mock_plan_get.return_value = fake_plan
        result = plan.read_plan_from_db(
            self.context, fake_object.fake_plan_dict['plan_id'])
        self.assertIn('original_dependencies', result)
        self.assertIn('updated_dependencies', result)

    @mock.patch.object(db_api, 'plan_update')
    def test_update_plan_to_db(self, mock_plan_update):
        fake_plan_dict = copy.deepcopy(fake_object.fake_plan_dict)
        plan.update_plan_to_db(self.context,
                               fake_plan_dict['plan_id'],
                               fake_plan_dict)
        mock_plan_update.assert_called_once()
