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
from conveyor.clone.resources import common
from conveyor.common import config
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.conveyorheat.api import api
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context
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
        undo_mgr = utils.UndoManager()
        template = fake_constants.FAKE_PLAN['updated_resources']
        stack = resource.Resource.from_dict(template['stack_0'])
        self.manager.heat_api.get_resource = mock.MagicMock()
        self.manager.heat_api.get_resource.return_value = \
            api.Resource(api.format_resource(fake_constants.FAKE_RESOURCE))
        self.manager.compute_api.get_server = mock.MagicMock()
        self.manager.compute_api.get_server.return_value = \
            {'OS-EXT-STS:vm_state': 'active'}
        self.assertEqual(
            None,
            self.manager.add_extra_properties_for_stack(
                self.context, stack, False, True, undo_mgr
            ))

    @mock.patch.object(base_driver.BaseDriver, '_wait_for_volume_status')
    @mock.patch.object(birdiegatewayclient, 'get_birdiegateway_client')
    def test_handle_server_after_clone(self, mock_client, mock_wait):
        template = \
            fake_constants.FAKE_INSTANCE_TEMPLATE['template']['resources']
        template['volume_1']['extra_properties']['sys_clone'] = True
        self.manager.compute_api.migrate_interface_detach = mock.MagicMock()
        self.manager.compute_api.migrate_interface_detach.return_value = None
        mock_client.return_value = birdiegatewayclient.Client()
        mock_client.return_value.vservices._force_umount_disk = \
            mock.MagicMock()
        mock_client.return_value.vservices._force_umount_disk.return_value = \
            None
        self.manager.compute_api.stop_server = mock.MagicMock()
        self.manager.compute_api.stop_server.return_value = None
        self.manager.compute_api.detach_volume = mock.MagicMock()
        self.manager.compute_api.detach_volume.return_value = None
        common.ResourceCommon._await_instance_status = mock.MagicMock()
        common.ResourceCommon._await_instance_status.return_value = None
        self.manager.compute_api.attach_volume = mock.MagicMock()
        self.manager.compute_api.attach_volume.return_value = None
        self.manager.compute_api.start_server = mock.MagicMock()
        self.manager.compute_api.start_server.return_value = None
        self.assertEqual(
            None,
            self.manager.handle_server_after_clone(
                self.context, template['server_0'], template
            ))

    def test_handle_stack_after_clone(self):
        template = \
            fake_constants.FAKE_PLAN['updated_resources']['stack_0']
        self.assertEqual(
            None,
            self.manager.handle_stack_after_clone(
                self.context, template, {}
            ))
