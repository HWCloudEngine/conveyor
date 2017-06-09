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

from conveyor.clone.resources import common
from conveyor.clone.resources.volume.driver import volume
from conveyor.common import config
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context
from conveyor import utils

CONF = config.CONF


class VolumeCloneDriverTestCase(test.TestCase):
    def setUp(self):
        super(VolumeCloneDriverTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = volume.VolumeCloneDriver()

    @mock.patch.object(birdiegatewayclient, 'get_birdiegateway_client')
    def test_start_volume_clone(self, mock_client):
        def set_plan_state(arg1, arg2, arg3, arg4):
            pass

        self.manager.cinder_api.get = mock.MagicMock()
        self.manager.cinder_api.get.return_value = \
            {'status': 'available', 'shareable': False,
             'availability_zone': 'az01'}
        utils.get_next_vgw = mock.MagicMock()
        utils.get_next_vgw.return_value = ('123', '10.0.0.1')
        mock_client.return_value = birdiegatewayclient.Client()
        mock_client.return_value.vservices.get_disk_name = mock.MagicMock()
        mock_client.return_value.vservices.get_disk_name.return_value = \
            {'dev_name': 's'}
        self.manager.compute_api.attach_volume = mock.MagicMock()
        self.manager.compute_api.attach_volume.return_value = None
        mock_client.return_value.vservices.clone_volume = mock.MagicMock()
        mock_client.return_value.vservices.clone_volume.return_value = \
            {'body': {'task_id': '123'}}
        mock_client.return_value.vservices._force_umount_disk = \
            mock.MagicMock()
        mock_client.return_value.vservices._force_umount_disk.return_value = \
            None
        # common.ResourceCommon = mock.MagicMock()
        # common.ResourceCommon.return_value = common.ResourceCommon()
        self.manager.compute_api.stop_server = mock.MagicMock()
        self.manager.compute_api.stop_server.return_value = None
        common.ResourceCommon._await_instance_status = mock.MagicMock()
        common.ResourceCommon._await_instance_status.return_value = None
        self.manager.compute_api.detach_volume = mock.MagicMock()
        self.manager.compute_api.detach_volume.return_value = None
        self.manager.compute_api.start_server = mock.MagicMock()
        self.manager.compute_api.start_server.return_value = None
        self.assertEqual(None, self.manager.start_volume_clone(
            self.context, 'volume_0',
            fake_constants.UPDATED_TEMPLATE['template'],
            set_plan_state=set_plan_state))
