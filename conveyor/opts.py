# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import itertools

from conveyor.clone import manager as clone_manager
from conveyor.clone.resources import common as clone_resources_common
from conveyor.clone.resources.instance import manager as cri_manager
from conveyor.clone.resources.volume import manager as crv_manager
from conveyor.common import config
from conveyor.compute import nova
from conveyor.conveyoragentclient.v1 import client as conveyoragentclient
from conveyor.conveyorcaa import api as conveyorcaa_api
from conveyor.conveyorheat.common import config as conveyorheat_config
from conveyor.heat import heat
from conveyor.image import glance
from conveyor.network import neutron
from conveyor.volume import cinder


def list_opts():
    _opts = [
        ('DEFAULT',
            itertools.chain(
                config.core_opts,
                config.global_opts,
                config.birdie_opts,
                nova.nova_opts,
                conveyoragentclient.client_opts,
                conveyorheat_config.ces_client_opts,
                clone_manager.manager_opts,
                clone_manager.clone_opts,
                clone_resources_common.migrate_manager_opts,
                cri_manager.migrate_manager_opts,
                crv_manager.migrate_manager_opts,
            )),
        ('keystone_authtoken',
            itertools.chain(
                config.keystone_auth_opts
            )),
        ('conveyor_caa',
            itertools.chain(
                conveyorcaa_api.conveyorcaa_opts
            )),
        ('cinder',
            itertools.chain(
                cinder.cinder_opts
            )),
        ('glance',
            itertools.chain(
                glance.glance_opts
            )),
        ('heat',
            itertools.chain(
                heat.heat_opts
            )),
        ('neutron',
            itertools.chain(
                neutron.neutron_opts
            )),
    ]
    _opts.extend(list(conveyorheat_config.list_opts()))
    return _opts
