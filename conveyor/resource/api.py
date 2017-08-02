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

import numbers
import six

from oslo_log import log as logging

from conveyor.common import plan_status as p_status
from conveyor import exception
from conveyor.resource import rpcapi

LOG = logging.getLogger(__name__)


class ResourceAPI(object):

    def __init__(self):
        self.resource_rpcapi = rpcapi.ResourceAPI()
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

    def build_resources_topo(self, context, plan_id,
                             az_map, search_opt=None):
        return self.resource_rpcapi.build_resources_topo(context, plan_id,
                                                         az_map,
                                                         search_opt=search_opt)

    def get_resource_detail(self, context, resource_type, resource_id):
        LOG.info("Get %s resource details with id of <%s>.",
                 resource_type, resource_id)
        return self.resource_rpcapi.get_resource_detail(context,
                                                        resource_type,
                                                        resource_id)

    def list_clone_resources_attribute(self, context, plan_id, attribute):
        return self.resource_rpcapi.list_clone_resources_attribute(context,
                                                                   plan_id,
                                                                   attribute)

    def build_resources(self, context, resources):
        return self.resource_rpcapi.build_resources(context, resources)

    def replace_resources(self, context, resources,
                          ori_res, ori_dep):
        LOG.info("replace resources with values: %s", resources)

        if not isinstance(resources, list):
            msg = "'resources' argument must be a list."
            LOG.error(msg)
            raise exception.PlanUpdateError(message=msg)

        # Verify resources
        for res in resources:
            if not isinstance(res, dict):
                msg = "Every resource to be replaced must be a dict."
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

            # Simply parse value.
            for k, v in res.items():
                if v == 'true':
                    res[k] = True
                elif v == 'false':
                    res[k] = False
                elif isinstance(v, six.string_types):
                    try:
                        new_value = eval(v)
                        if type(new_value) in (dict, list, numbers.Number):
                            res[k] = new_value
                    except Exception:
                        pass

        return self.resource_rpcapi.replace_resources(
            context, resources, ori_res, ori_dep)

    def update_resources(self, context, data_copy, resources,
                          ori_res, ori_dep):
        LOG.info("update resources with values: %s", resources)
        if not isinstance(resources, list):
            msg = "'resources' argument must be a list."
            LOG.error(msg)
            raise exception.PlanUpdateError(message=msg)

        # Verify resources
        for res in resources:
            if not isinstance(res, dict):
                msg = "Every resource to be replaced must be a dict."
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

            # Simply parse value.
            for k, v in res.items():
                if v == 'true':
                    res[k] = True
                elif v == 'false':
                    res[k] = False
                elif isinstance(v, six.string_types):
                    try:
                        new_value = eval(v)
                        if type(new_value) in (dict, list, numbers.Number):
                            res[k] = new_value
                    except Exception:
                        pass

        return self.resource_rpcapi.update_resources(
            context, data_copy, resources, ori_res, ori_dep)
