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

from conveyor.clone.drivers import driver
from conveyor.clone.resources import common
from conveyor.common import config
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context
from conveyor import utils

CONF = config.CONF


class BaseDriverTestCase(test.TestCase):
    def setUp(self):
        super(BaseDriverTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = driver.BaseDriver()

    def test_add_extra_properties_for_volume_with_vm(self):
        template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
        res_map = {}
        for key, value in template['resources'].items():
            res_map[key] = resource.Resource.from_dict(value)
        undo_mgr = utils.UndoManager()
        self.assertEqual(
            None,
            self.manager.add_extra_properties_for_volume(
                self.context,
                'volume_1', res_map['volume_1'],
                res_map,
                False, True, undo_mgr))

    @mock.patch.object(birdiegatewayclient, 'get_birdiegateway_client')
    def test_add_extra_properties_for_volume(self, mock_client):
        template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
        res_map = dict()
        res_map['volume_1'] = \
            resource.Resource.from_dict(template['resources']['volume_1'])
        undo_mgr = utils.UndoManager()
        self.manager.volume_api.get = mock.MagicMock()
        self.manager.volume_api.get.return_value = \
            {'status': 'available',
             'shareable': True,
             'attachments': [{'server_id': '123'}]}
        res_map['volume_1'].extra_properties.pop('gw_url')
        utils.get_next_vgw = mock.MagicMock()
        utils.get_next_vgw.return_value = ('123', '10.0.0.1')
        mock_client.return_value = birdiegatewayclient.Client()
        mock_client.return_value.vservices.get_disk_name = mock.MagicMock()
        mock_client.return_value.vservices.get_disk_name.return_value = \
            {'dev_name': 's'}
        self.manager.compute_api.attach_volume = mock.MagicMock()
        self.manager.compute_api.attach_volume.return_value = None
        mock_client.return_value.vservices.get_disk_format = mock.MagicMock()
        mock_client.return_value.vservices.get_disk_format.return_value = \
            {'disk_format': 'ext3'}
        mock_client.return_value.vservices.force_mount_disk = mock.MagicMock()
        mock_client.return_value.vservices.force_mount_disk.return_value = \
            {'mount_disk': '/opt'}
        self.assertEqual(
            None,
            self.manager.add_extra_properties_for_volume(
                self.context,
                'volume_1', res_map['volume_1'],
                res_map,
                False, True, undo_mgr))

    def test_handle_volume_after_clone_with_vm(self):
        template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
        self.assertEqual(
            None,
            self.manager.handle_volume_after_clone(
                self.context,
                template['resources']['volume_1'], 'volume_1',
                template['resources']))

    # def test_handle_volume_after_clone(self):
    #     template = fake_constants.FAKE_INSTANCE_TEMPLATE['template']
    #     common.ResourceCommon = mock.MagicMock()
    #     common.ResourceCommon.return_value = common.ResourceCommon()
    #     common.ResourceCommon._await_instance_status = mock.MagicMock()
    #     common.ResourceCommon._await_instance_status.return_value = None
    #     self.manager.compute_api.stop_server = mock.MagicMock()
    #     self.manager.compute_api.stop_server.return_value = None
    #     self.manager.compute_api.detach_volume = mock.MagicMock()
    #     self.manager.compute_api.detach_volume.return_value = None
    #     self.manager.volume_api.get = mock.MagicMock()
    #     self.manager.volume_api.get.return_value = \
    #         {'status': 'available',
    #          'shareable': True,
    #          'attachments': []}
    #     self.manager.compute_api.start_server = mock.MagicMock()
    #     self.manager.compute_api.start_server.return_value = None
    #
    #     self.assertEqual(
    #         None,
    #         self.manager.handle_volume_after_clone(
    #             self.context,
    #             template['resources']['volume_1'], 'volume_1',
    #             template['resources']))
