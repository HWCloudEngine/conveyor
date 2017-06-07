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

from conveyor.clone.resources import common as resource_comm
from conveyor.common import config
from conveyor.common import plan_status
from conveyor.conveyoragentclient.v1 import client as conveyorclient
from conveyor.tests import test

from conveyor import context
from conveyor import exception

CONF = config.CONF


class ResourceCommonTestCase(test.TestCase):
    def setUp(self):
        super(ResourceCommonTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = resource_comm.ResourceCommon()

    def test_await_volume_status(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.volume_api.get = mock.MagicMock()
        self.manager.volume_api.get.return_value = {'status': 'available'}
        self.assertEqual(1, self.manager._await_volume_status(
            self.context,
            '123', 'available'))

    def test_await_volume_status_with_raise(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.volume_api.get = mock.MagicMock()
        self.manager.volume_api.get.return_value = {'status': 'in-use'}
        self.assertRaises(exception.VolumeNotdetach,
                          self.manager._await_volume_status,
                          self.context, '123', 'available')

    def test_await_data_trans_status_without_host(self):
        CONF.set_default('data_transformer_state_retries', 1)
        self.manager.resource_api.update_plan = mock.MagicMock()
        self.manager.resource_api.update_plan.return_value = None
        self.assertEqual(
            0,
            self.manager._await_data_trans_status(self.context,
                                                  None, None, [123],
                                                  plan_status.STATE_MAP))

    @mock.patch.object(conveyorclient, 'get_birdiegateway_client')
    def test_await_data_trans_status_with_host(self, mock_con_client):
        mock_con_client.return_value = conveyorclient.Client()
        mock_con_client.return_value.vservices.get_data_trans_status = \
            mock.MagicMock()
        mock_con_client.return_value. \
            vservices.get_data_trans_status.return_value = \
            {'body': {'task_state': 'DATA_TRANS_FINISHED'}}
        CONF.set_default('data_transformer_state_retries', 1)
        CONF.set_default('data_transformer_state_retries_interval', 0.1)
        self.manager.resource_api.update_plan = mock.MagicMock()
        self.manager.resource_api.update_plan.return_value = None
        self.assertEqual(
            1,
            self.manager._await_data_trans_status(self.context,
                                                  123, 80, [123],
                                                  plan_status.STATE_MAP))

    @mock.patch.object(conveyorclient, 'get_birdiegateway_client')
    def test_await_data_trans_status_with_raise(self, mock_con_client):
        mock_con_client.return_value = conveyorclient.Client()
        mock_con_client.return_value.vservices.get_data_trans_status = \
            mock.MagicMock()
        mock_con_client.return_value. \
            vservices.get_data_trans_status.return_value = \
            {'body': {'task_state': 'DATA_TRANSFORMING'}}
        CONF.set_default('data_transformer_state_retries', 1)
        CONF.set_default('data_transformer_state_retries_interval', 0.1)
        self.manager.resource_api.update_plan = mock.MagicMock()
        self.manager.resource_api.update_plan.return_value = None
        self.assertRaises(
            exception.InstanceNotCreated,
            self.manager._await_data_trans_status,
            self.context, 123, 80, [123], plan_status.STATE_MAP)

    def test_await_block_device_map_created(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.volume_api.get = mock.MagicMock()
        self.manager.volume_api.get.return_value = {'status': 'available'}
        self.assertEqual(1, self.manager._await_block_device_map_created(
            self.context, '123'))

    def test_await_block_device_map_created_with_raise(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.volume_api.get = mock.MagicMock()
        self.manager.volume_api.get.return_value = {'status': 'downloading'}
        self.assertRaises(exception.VolumeNotCreated,
                          self.manager._await_block_device_map_created,
                          self.context, '123')

    def test_await_instance_create(self):
        CONF.set_default('instance_allocate_retries', 1)
        CONF.set_default('instance_create_retries_interval', 0.1)
        self.manager.nova_api.get_server = mock.MagicMock()
        self.manager.nova_api.get_server.return_value = {'status': 'ACTIVE'}
        self.assertEqual(1, self.manager._await_instance_create(
            self.context, '123'))

    def test_await_instance_create_with_raise(self):
        CONF.set_default('instance_allocate_retries', 1)
        CONF.set_default('instance_create_retries_interval', 0.1)
        self.manager.nova_api.get_server = mock.MagicMock()
        self.manager.nova_api.get_server.return_value = {'status': 'BOOTING'}
        self.assertRaises(exception.InstanceNotCreated,
                          self.manager._await_instance_create,
                          self.context, '123')

    def test_await_instance_status(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.nova_api.get_server = mock.MagicMock()
        self.manager.nova_api.get_server.return_value = {'status': 'ACTIVE'}
        self.assertEqual(1, self.manager._await_instance_status(
            self.context, '123', 'ACTIVE'))

    def test_await_instance_status_with_raise(self):
        CONF.set_default('block_device_allocate_retries', 1)
        CONF.set_default('block_device_allocate_retries_interval', 0.1)
        self.manager.nova_api.get_server = mock.MagicMock()
        self.manager.nova_api.get_server.return_value = {'status': 'SHUTOFF'}
        self.assertRaises(exception.InstanceNotStart,
                          self.manager._await_instance_status,
                          self.context, '123', 'ACTIVE')

    def test_await_port_status(self):
        CONF.set_default('port_allocate_retries', 1)
        CONF.set_default('port_allocate_retries_interval', 0.1)
        self.manager.conveyor_cmd.check_ip_connect = mock.MagicMock()
        self.manager.conveyor_cmd.check_ip_connect.return_value = 1
        self.assertEqual(1, self.manager._await_port_status(
            self.context, '123', '10.0.0.1'))

    def test_await_port_status_with_raise(self):
        CONF.set_default('port_allocate_retries', 1)
        CONF.set_default('port_allocate_retries_interval', 0.1)
        self.manager.conveyor_cmd.check_ip_connect = mock.MagicMock()
        self.manager.conveyor_cmd.check_ip_connect.return_value = 0
        self.assertRaises(exception.PortNotattach,
                         self.manager._await_port_status,
                         self.context, '123', '10.0.0.1')
