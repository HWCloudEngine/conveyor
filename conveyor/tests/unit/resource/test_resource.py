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
import sys

if sys.version_info >= (3, 0):
    import builtins as builtin
else:
    import __builtin__ as builtin

from oslo_serialization import jsonutils

from conveyor import context
from conveyor.db import api as db_api
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object


class ResourceTestCase(test.TestCase):

    def setUp(self):
        super(ResourceTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)

    @mock.patch.object(db_api, 'plan_create')
    @mock.patch.object(jsonutils, 'dump')
    @mock.patch.object(builtin, 'open')
    def test_save_plan_to_db(self, mock_open, mock_dump, mock_plan_create):
        resource.save_plan_to_db(self.context, '/var/lib/conveyor',
                                 fake_object.fake_plan_dict)
        mock_plan_create.assert_called_once()

    @mock.patch.object(jsonutils, 'load')
    @mock.patch.object(builtin, 'open')
    @mock.patch.object(db_api, 'plan_get')
    def test_read_plan_from_db(self, mock_plan_get, mock_open, mock_load):
        mock_plan_get.return_value = fake_object.fake_plan_dict
        result = resource.read_plan_from_db(
            self.context, fake_object.fake_plan_dict['plan_id'])
        self.assertEqual(resource.Plan, type(result[1]))

    @mock.patch.object(db_api, 'plan_update')
    @mock.patch.object(jsonutils, 'dump')
    @mock.patch.object(builtin, 'open')
    def test_update_plan_to_db(self, mock_open, mock_dump, mock_plan_update):
        fake_plan_dict = copy.deepcopy(fake_object.fake_plan_dict)
        resource.update_plan_to_db(self.context, '/var/lib/conveyor',
                                   fake_plan_dict['plan_id'],
                                   fake_plan_dict)
        self.assertNotIn('original_dependencies', fake_plan_dict)
        self.assertNotIn('updated_dependencies', fake_plan_dict)
        mock_plan_update.assert_called_once()
