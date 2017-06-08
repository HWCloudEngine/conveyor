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

from conveyor.clone.drivers import driver as base_driver
from conveyor.clone.drivers.openstack import driver
from conveyor.common import config
from conveyor.common import plan_status
from conveyor.conveyoragentclient.v1 import client as conveyorclient
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context
from conveyor import exception
from conveyor import utils

CONF = config.CONF


class OpenstackDriverTestCase(test.TestCase):
    def setUp(self):
        super(OpenstackDriverTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = driver.OpenstackDriver()

    def test_handle_resources(self):
        pass

    @mock.patch.object(base_driver.BaseDriver, '_handle_dv_for_svm')
    def test_add_extra_properties_for_server(self, mock_svm):
        template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
        template['resources']['server_0']['extra_properties'].pop('gw_url')
        res_map = {}
        for key, value in template['resources'].items():
            res_map[key] = resource.Resource.from_dict(value)
        undo_mgr = utils.UndoManager()
        utils.get_next_vgw = mock.MagicMock()
        utils.get_next_vgw.return_value = ('123', '10.0.0.1')
        self.assertEqual(
            None,
            self.manager.add_extra_properties_for_server(
                self.context, res_map['server_0'], res_map,
                False, True, undo_mgr))

    @mock.patch.object(base_driver.BaseDriver, '_handle_dv_for_svm')
    def test_add_extra_properties_for_server_with_active(self, mock_svm):
        template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
        template['resources']['server_0']['extra_properties'].pop('gw_url')
        template['resources']['server_0']['extra_properties']['vm_state'] = \
            'active'
        res_map = {}
        for key, value in template['resources'].items():
            res_map[key] = resource.Resource.from_dict(value)
        undo_mgr = utils.UndoManager()
        utils.get_next_vgw = mock.MagicMock()
        utils.get_next_vgw.return_value = ('123', '10.0.0.1')
        self.assertEqual(
            None,
            self.manager.add_extra_properties_for_server(
                self.context, res_map['server_0'], res_map,
                False, True, undo_mgr))

    def test_add_extra_properties_for_stack(self):
        pass

    def test_handle_server_after_clone(self):
        pass

    def test_handle_stack_after_clone(self):
        pass
