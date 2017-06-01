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
import yaml

from conveyor.clone import manager
from conveyor.common import config
from conveyor.conveyorheat.api import api
from conveyor.db import api as db_api
from conveyor.resource import api as resource_api
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context
from conveyor import exception
from conveyor.resource import resource

CONF = config.CONF
# resource_from_dict = resource.Resource.from_dict


class CloneManagerTestCase(test.TestCase):

    def setUp(self):
        super(CloneManagerTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.clone_manager = manager.CloneManager()

    def test_start_template_clone(self):
        CONF.set_default('clone_migrate_type', 'cold')
        self.clone_manager.heat_api.create_stack = mock.MagicMock()
        self.clone_manager.heat_api.create_stack.return_value = \
            fake_constants.FAKE_STACK
        db_api.plan_stack_create = mock.MagicMock()
        db_api.plan_stack_create.return_value = None
        self.clone_manager.resource_api.update_plan = mock.MagicMock()
        self.clone_manager.resource_api.update_plan.return_value = None
        self.clone_manager.heat_api.events_list = mock.MagicMock()
        self.clone_manager.heat_api.events_list.return_value = \
            [api.Event(api.format_event(fake_constants.FAKE_EVENT_LIST))]
        self.clone_manager.heat_api.get_resource = mock.MagicMock()
        self.clone_manager.heat_api.get_resource.return_value = \
            api.Resource(api.format_resource(fake_constants.FAKE_RESOURCE))
        self.clone_manager.clone_managers.get('volume').\
            start_template_clone = mock.MagicMock()
        self.clone_manager.clone_managers.get('volume').\
            start_template_clone.return_value = None
        with test.nested(
                mock.patch.object(
                    self.clone_manager.heat_api, 'get_stack',
                    return_value=api.Stack(
                        api.format_stack(fake_constants.FAKE_STACK_STATUS))),
                mock.patch.object(resource_api.ResourceAPI,
                                  "get_plan_by_id")):
            ret = self.clone_manager.start_template_clone(
                self.context,
                fake_constants.UPDATED_TEMPLATE)
            self.assertEqual(fake_constants.FAKE_STACK['stack']['id'], ret)

    def test_start_template_clone_error(self):
        CONF.set_default('clone_migrate_type', 'cold')
        self.clone_manager.heat_api.create_stack = mock.MagicMock()
        self.clone_manager.heat_api.create_stack.side_effect = \
            exception.PlanDeployError
        self.assertRaises(exception.PlanDeployError,
                          self.clone_manager.start_template_clone,
                          self.context,
                          fake_constants.UPDATED_TEMPLATE)

    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_export_clone_template_error(self, get_plan_by_id_mock):
        get_plan_by_id_mock.return_value = None
        fake_id = 'fake-001'
        sys_clone = False
        self.assertRaises(exception.PlanNotFound,
                          self.clone_manager.export_clone_template,
                          self.context, fake_id, sys_clone, True)

    @mock.patch.object(resource_api.ResourceAPI, "update_plan")
    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_export_clone_template(self, mock_plan, mock_update):
        mock_plan.return_value = fake_constants.FAKE_PLAN
        mock_update.return_value = None
        res = resource.Resource('test', 'test', 'test')
        manager.resource_from_dict = mock.MagicMock()
        manager.resource_from_dict.return_value = res
        sys_clone = False
        fake_id = 'fake-001'
        self.clone_manager.clone_driver.handle_resources = mock.MagicMock()
        self.clone_manager.clone_driver.handle_resources.return_value = None
        yaml.safe_dump = mock.MagicMock()
        yaml.safe_dump.return_value = None
        ret = ({'stack_0': res}, '2017-05-22 02:01:59.136794')
        with mock.patch("__builtin__.open", create=True) as mock_open:
            mock_open.side_effect = \
                mock.mock_open(read_data="Data1").return_value
            self.assertEqual(
                ret,
                self.clone_manager.export_clone_template(self.context,
                                                         fake_id, sys_clone,
                                                         True))

    @mock.patch.object(resource_api.ResourceAPI, "update_plan")
    @mock.patch.object(resource_api.ResourceAPI, "get_plan_by_id")
    def test_clone(self, mock_plan, mock_update):
        mock_plan.return_value = fake_constants.FAKE_PLAN
        mock_update.return_value = None
        res = resource.Resource('test', 'test', 'test')
        manager.resource_from_dict = mock.MagicMock()
        manager.resource_from_dict.return_value = res
        self.clone_manager.start_template_clone = mock.MagicMock()
        self.clone_manager.start_template_clone.return_value = '123'


    def test_clone_error(self):
        pass

    def test_migrate(self):
        pass

    def test_migrate_error(self):
        pass

    def test_download_template(self):
        pass

    def test_download_template_error(self):
        pass
