# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
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

from conveyor import compute
from conveyor.clone.drivers import driver
from conveyor.conveyoragentclient.v1 import client as birdiegatewayclient
from conveyor import exception
from conveyor import heat
from conveyor.i18n import _LE
from conveyor import network
from conveyor import utils
from conveyor import volume


class AwsDriver(driver.BaseDriver):
    def __init__(self):
        self.volume_api = volume.API()
        self.compute_api = compute.API()
        self.neutron_api = network.API()
        self.heat_api = heat.API()
