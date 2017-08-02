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


class Resource(object):
    def __init__(self, context):
        self.context = context
        self._tenant_id = self.context.project_id
        self._collected_resources = {}
        self._collected_parameters = {}
        self._collected_dependencies = {}

    def get_collected_resources(self):
        return self._collected_resources

    def get_collected_dependencies(self):
        return self._collected_dependencies

    def _get_resource_num(self, resource_type):
        num = -1
        for res in self._collected_resources.values():
            if resource_type == res.type:
                n = res.name.split('_')[-1]
                try:
                    n = int(n)
                    num = n if n > num else num
                except Exception:
                    pass
        return num + 1

    def _get_parameter_num(self):
        return len(self._collected_parameters)

    def _get_resource_by_name(self, name):
        for res in self.get_collected_resources().values():
            if res.name == name:
                return res
        return None

    def _tenant_filter(self, res):
        tenant_id = res.get('tenant_id')
        if not tenant_id:
            raise "%s object has no attribute 'tenant_id' " % res.__class__
        return tenant_id == self._tenant_id
