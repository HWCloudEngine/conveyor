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

"""
WSGI middleware for Hybrid-conveyor API.
"""

from oslo_log import log as logging

from conveyor.api import extensions
import conveyor.api.wsgi

from conveyor.api.v1 import clone
from conveyor.api.v1 import migrate
from conveyor.api.v1 import plans
from conveyor.api.v1 import resources


LOG = logging.getLogger(__name__)


class APIRouter(conveyor.api.wsgi.APIRouter):
    """Routes requests on the API to the appropriate controller and method."""
    ExtensionManager = extensions.ExtensionManager

    def _setup_routes(self, mapper, ext_mgr):
        self.resources['clones'] = clone.create_resource(ext_mgr)
        mapper.resource("clone", "clones",
                        controller=self.resources['clones'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})

        self.resources['migrates'] = migrate.create_resource(ext_mgr)
        mapper.resource("migrate", "migrates",
                        controller=self.resources['migrates'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})

        self.resources['resources'] = resources.create_resource(ext_mgr)
        mapper.resource("resource", "resources",
                        controller=self.resources['resources'],
                        collection={'detail': 'GET', 'types': 'GET'},
                        member={'action': 'POST'})

        self.resources['plans'] = plans.create_resource(ext_mgr)
        mapper.resource("plan", "plans",
                        controller=self.resources['plans'],
                        collection={'detail': 'GET',
                                    'create_plan_by_template': 'POST'},
                        member={'action': 'POST'})
