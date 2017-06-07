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

from conveyor.clone.resources.instance.driver import stack_template
from conveyor.common import config
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor.conveyorheat.api import api
from conveyor.tests import test
from conveyor.tests.unit import fake_constants

from conveyor import context

CONF = config.CONF


class StackTemplateCloneDriverTestCase(test.TestCase):
    def setUp(self):
        super(StackTemplateCloneDriverTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = stack_template.StackTemplateCloneDriver()

    @mock.patch.object(birdiegatewayclient, 'get_birdiegateway_client')
    def test_start_template_clone(self, mock_client):
        self.manager.nova_api.get_server = mock.MagicMock()
        self.manager.nova_api.get_server.return_value = \
            {'OS-EXT-AZ:availability_zone': 'az01',
             'id': '123'}
        self.manager.heat_api.get_resource = mock.MagicMock()
        self.manager.heat_api.get_resource.return_value = \
            api.Resource(api.format_resource(fake_constants.FAKE_RESOURCE))
        self.manager.neutron_api.port_list = mock.MagicMock()
        self.manager.neutron_api.port_list.return_value = \
            [{'binding:profile': {'host_ip': '10.1.1.1'}}]
        mock_client.return_value = birdiegatewayclient.Client()
        mock_client.return_value.vservices.get_disk_name = mock.MagicMock()
        mock_client.return_value.vservices.get_disk_name.return_value = \
            {'dev_name': 's'}
        mock_client.return_value.vservices.get_disk_format = mock.MagicMock()
        mock_client.return_value.vservices.get_disk_format.return_value = \
            {'disk_format': 'ext3'}
        mock_client.return_value.vservices.get_disk_mount_point = \
            mock.MagicMock()
        mock_client.return_value.vservices.\
            get_disk_mount_point.return_value = {'mount_point': '/opt'}
        mock_client.return_value.vservices.clone_volume = mock.MagicMock()
        mock_client.return_value.vservices.clone_volume.return_value = \
            {'body': {'task_id': '123'}}
        self.assertEqual(None, self.manager.start_template_clone(
            self.context, 'server_0',
            fake_constants.FAKE_INSTANCE_TEMPLATE['template']))

    def test_start_template_migrate(self):
        pass
