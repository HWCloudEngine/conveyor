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

import six

from oslo_log import log as logging

from conveyor import exception

LOG = logging.getLogger(__name__)


class Resource(object):
    """Describes an OpenStack resource."""

    def __init__(self, name, type, id, properties=None,
                 extra_properties=None, parameters=None):
        self.name = name
        self.type = type
        self.id = id or ""
        self.properties = properties or {}
        self.extra_properties = extra_properties or {}
        self.parameters = parameters or {}
        self.extra_properties['id'] = self.id

    def add_parameter(self, name, description, parameter_type='string',
                      constraints=None, default=None):
        data = {
            'type': parameter_type,
            'description': description,
        }

        if default:
            data['default'] = default

        self.parameters[name] = data

    def add_property(self, key, value):
        self.properties[key] = value

    def add_extra_property(self, key, value):
        self.extra_properties[key] = value

    @property
    def template_resource(self):
        return {
            self.name: {
                'type': self.type,
                'properties': self.properties,
                'extra_properties': self.extra_properties
            }
        }

    @property
    def template_parameter(self):
        return self.parameters

    def to_dict(self):
        resource = {
                  "id": self.id,
                  "name": self.name,
                  "type": self.type,
                  "properties": self.properties,
                  "extra_properties": self.extra_properties,
                  "parameters": self.parameters
                  }
        return resource

    @classmethod
    def from_dict(cls, resource_dict):
        self = cls(resource_dict['name'],
                   resource_dict['type'], resource_dict['id'],
                   properties=resource_dict.get('properties'),
                   extra_properties=resource_dict.get('extra_properties'),
                   parameters=resource_dict.get('parameters'))
        return self

    def rebuild_parameter(self, parameters):

        def get_params(properties):
            if isinstance(properties, dict) and len(properties) == 1:
                key = properties.keys()[0]
                value = properties[key]
                if key == "get_param":
                    if isinstance(value, six.string_types) and \
                                    value in parameters.keys():
                        param = parameters[value]
                        self.add_parameter(
                            value,
                            param.get('description', ''),
                            parameter_type=param.get('type', 'string'),
                            constraints=param.get('constraints', ''),
                            default=param.get('default', ''))
                    else:
                        msg = ("Parameter %s is invalid or "
                               "not found." % value)
                        LOG.error(msg)
                        raise exception.ParameterNotFound(message=msg)
                else:
                    get_params(properties[key])
            elif isinstance(properties, dict):
                for p in properties.values():
                    get_params(p)
            elif isinstance(properties, list):
                for p in properties:
                    get_params(p)

        if not isinstance(parameters, dict):
            return
        self.parameters = {}
        get_params(self.properties)


class ResourceDependency(object):
    def __init__(self, id, name, name_in_template,
                 type, dependencies=None):
        self.id = id
        self.name = name
        self.name_in_template = name_in_template
        self.type = type
        self.dependencies = dependencies or []

    def add_dependency(self, res_name):
        if res_name not in self.dependencies:
            self.dependencies.append(res_name)

    def to_dict(self):
        dep = {
               "id": self.id,
               "name": self.name,
               "type": self.type,
               "name_in_template": self.name_in_template,
               "dependencies": self.dependencies
               }

        return dep

    @classmethod
    def from_dict(cls, dep_dict):
        self = cls(dep_dict['id'],
                   dep_dict['name'],
                   dep_dict['name_in_template'],
                   dep_dict['type'],
                   dependencies=dep_dict.get('dependencies'))
        return self
