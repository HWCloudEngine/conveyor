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


from oslo_log import log as logging

from conveyor.common import plan_status as p_status
from conveyor.plan import api as plan_api
from conveyor.resource import rpcapi

LOG = logging.getLogger(__name__)


class ResourceAPI(object):

    def __init__(self):
        self.resource_rpcapi = rpcapi.ResourceAPI()
        self._plan_api = plan_api.PlanAPI()
        super(ResourceAPI, self).__init__()

    def get_resource_types(self, context):
        LOG.info("Get resource types.")
        return p_status.RESOURCE_TYPES

    def get_resources(self, context, search_opts=None,
                      marker=None, limit=None):
        LOG.info("Get resources filtering by: %s", search_opts)
        return self.resource_rpcapi.get_resources(context,
                                                  search_opts=search_opts,
                                                  marker=marker, limit=limit)

    def build_reources_topo(self, context, resources):
        LOG.info("Create a %s plan by resources: %s.", type, resources)
        return self.resource_rpcapi.build_reources_topo(context, resources)

    def get_resource_detail(self, context, resource_type, resource_id):
        LOG.info("Get %s resource details with id of <%s>.",
                 resource_type, resource_id)
        return self.resource_rpcapi.get_resource_detail(context,
                                                        resource_type,
                                                        resource_id)

    def list_plan_resource_availability_zones(self, context, plan):
        if not isinstance(plan, dict):
            plan = self._plan_api.get_plan_by_id(context, plan, detail=True)

        res_azs = []
        plan_res = plan.get('original_resources')
        for key, res in plan_res.items():
            if res['type'] in ('OS::Nova::Server', 'OS::Cinder::Volume'):
                az = res['properties']['availability_zone']
                if az not in res_azs:
                    res_azs.append(az)
        return res_azs
