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

from conveyor.clone.drivers.openstack import driver
from conveyor.common import config
from conveyor.common import plan_status
from conveyor.conveyoragentclient.v1 import client as conveyorclient
from conveyor.tests import test

from conveyor import context
from conveyor import exception

CONF = config.CONF


class OpenstackDriverTestCase(test.TestCase):
    def setUp(self):
        super(OpenstackDriverTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.manager = driver.OpenstackDriver()

    def test_handle_resources(self):
        pass

    def test_add_extra_properties_for_server(self):
        pass

    def test_add_extra_properties_for_stack(self):
        pass

    def test_handle_server_after_clone(self):
        pass

    def test_handle_stack_after_clone(self):
        pass
