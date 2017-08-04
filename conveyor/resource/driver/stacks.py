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

import json

from oslo_log import log as logging

from conveyor import exception
from conveyor import heat
from conveyor.resource.driver import base
from conveyor.resource import resource as res

LOG = logging.getLogger(__name__)


class StackResource(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.heat_api = heat.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_stacks(self, stack_ids):

        stack_dicts = []
        stackResources = []
        if not stack_ids:
            LOG.info('Extract resources of all stacks.')
            return stackResources
        else:
            LOG.info('Extract resources of stacks: %s', stack_ids)
            # remove duplicate volume
            stack_ids = {}.fromkeys(stack_ids).keys()
            for stack_id in stack_ids:
                try:
                    stack = self.heat_api.get_stack(self.context, stack_id)
                    stack_dicts.append(stack)
                except Exception as e:
                    msg = "stack resource <%s> could not be found. %s" \
                            % (stack_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for stack in stack_dicts:
            stack_id = stack['id']
            stack_res = self._collected_resources.get(stack_id)
            if stack_res:
                stackResources.append(stack_res)
                continue
            properties = {}
            timeout_mins = stack['timeout_mins']
            if timeout_mins:
                properties['timeout'] = timeout_mins
            parameters = stack['parameters']
            if parameters and parameters.get('OS::stack_id'):
                parameters.pop('OS::stack_id')
                properties['parameters'] = parameters
            properties['disable_rollback'] = stack['disable_rollback']
            properties['stack_name'] = stack['stack_name']

            template = self._extract_resource(self.context, stack_id)
            template = json.loads(template)
            template_params = template.get('parameters')
            if template_params:
                for key in template_params.keys():
                    if parameters.get(key):
                        param_info = template_params[key]
                        param_info['default'] = parameters.get(key)
                        template_params[key] = param_info
            properties['template'] = json.dumps(template)

            resource_type = "OS::Heat::Stack"
            resource_name = 'stack_%d' % self._get_resource_num(resource_type)
            stack_res = res.Resource(resource_name, resource_type,
                                     stack_id, properties=properties)
            stack_dep = res.ResourceDependency(stack_id,
                                               resource_name,
                                               stack['stack_name'],
                                               resource_type)

            self._collected_resources[stack_id] = stack_res
            self._collected_dependencies[stack_id] = stack_dep

            stackResources.append(stack_res)

        if stack_ids and not stackResources:
            msg = "Stack resource extracted failed, \
                    can't find the stack with id of %s." % stack_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        LOG.info('Extracting stack resources has finished')

        return stackResources

    def _list_sub_resources(self, context, stack_id):
        return self.heat_api.resources_list(context, stack_id)

    def is_file_type(self, t):
        return t and t.startswith('file://')

    def get_resources(self, res_list, t):
        """filter by resource type. """
        return [r for r in res_list if r.resource_type == t]

    def _extract_resource(self, context, stack_id):
        template = self.heat_api.get_template(context, stack_id)
        sub_res_list = self._list_sub_resources(context, stack_id)
        for name, resource in template.get('resources', {}).iteritems():
            t1 = resource.get('type')
            if self.is_file_type(t1):
                extract_reses = self.get_resources(sub_res_list, t1)
                physical_resource_id = extract_reses[0].physical_resource_id
                extract_res = \
                    self._extract_resource(context,
                                           physical_resource_id)
                resource['content'] = extract_res
                resource['id'] = physical_resource_id
                continue
            r = resource.get('properties', {}).get('resource')
            if not r or not self.is_file_type(r.get('type')):
                continue
            t2 = r.get('type')
            found = None
            for sub in self.get_resources(sub_res_list, t1):
                sub_res_id = sub.physical_resource_id
                for descendant in self._list_sub_resources(context,
                                                           sub_res_id):
                    if descendant.resource_type == t2:
                        found = descendant.physical_resource_id
                        break
                if found:
                    # if is_exclude_type(t1):
                    content = self._extract_resource(context, found)
                    break
            resource['properties']['resource']['content'] = content
            resource['properties']['resource']['id'] = found

        return json.dumps(template)
