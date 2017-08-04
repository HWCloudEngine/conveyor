# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

from conveyor.resource.driver import base
from conveyor.resource import resource

LOG = logging.getLogger(__name__)


class HeatResource(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_resource(self, template, name, resource_type,
                         resource_id, stack_name=None,
                         parent_resources=None):
        if not template or not name or not resource_id:
            return
        LOG.debug('Extract resource of heat resource %s.', name)
        # If this heat resource has been extracted, ignore it.
        heat_resources = self._collected_resources.get(resource_id)
        if heat_resources:
            return heat_resources
        resource_name = name
        if stack_name and resource_id in parent_resources:
            resource_name = stack_name + '.' + resource_name
        heat_resources = resource.Resource(resource_name, resource_type,
                                           resource_id, properties={})

        template_resources = template.get('resources')
        t_resource = template_resources.get(name)
        properties = t_resource.get('properties')
        heat_resources.properties = properties
        resource_dependencies = resource.ResourceDependency(resource_id, name,
                                                            resource_name,
                                                            resource_type)
        self._collected_resources[resource_id] = heat_resources
        self._collected_dependencies[resource_id] = resource_dependencies

        return heat_resources
