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

import copy
import json
import yaml

from oslo_log import log as logging

from conveyor import exception
from conveyor import heat
from conveyor.resource.driver import base
from conveyor.resource.driver.heatresource import HeatResource
from conveyor.resource.driver.instances import InstanceResource
from conveyor.resource.driver.networks import NetworkResource
from conveyor.resource.driver.secgroup import SecGroup
from conveyor.resource.driver.volumes import Volume
from conveyor.resource.driver.volumes import VolumeType
from conveyor.resource import resource as res

LOG = logging.getLogger(__name__)


handle_resource_types = ['OS::Nova::Server', 'OS::Glance::Image',
                         'OS::Nova::Flavor', 'OS::Nova::KeyPair',
                         'OS::Cinder::Volume', 'OS::Neutron::Net',
                         'OS::Cinder::VolumeType',
                         'OS::Neutron::Subnet', 'OS::Neutron::Port',
                         'OS::Neutron::Router',
                         'OS::Neutron::LoadBalancer',
                         'OS::Neutron::FloatingIP',
                         'OS::Neutron::SecurityGroup',
                         'OS::Neutron::Pool', 'OS::Heat::Stack']


class StackResource(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.heat_api = heat.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_stacks(self, stack_ids):
        stack_lists = []
        stackResources = []
        stack_resources_dicts = {}
        if not stack_ids:
            LOG.info('Extract resources of all stacks.')
            stack_lists = self.heat_api.stack_list(self.context)
        else:
            LOG.info('Extract resources of stacks: %s', stack_ids)
            # remove duplicate volume
            stack_ids = {}.fromkeys(stack_ids).keys()
            for stack_id in stack_ids:
                try:
                    stack = self.heat_api.get_stack(self.context, stack_id)
                    stack_lists.append(stack)
                except Exception as e:
                    msg = "stack resource <%s> could not be found. %s" \
                        % (stack_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for stack in stack_lists:
            stack_id = stack['id']
            stack_res = self._collected_resources.get(stack_id)
            if stack_res:
                stackResources.append(stack_res)
                continue
            # extract stack and return resource
            stack_resources_dicts[stack_id] = self._extract_stack_resources(
                self.context, stack)
        for _resources in stack_resources_dicts.values():
            for _res in _resources:
                self._collected_resources.pop(_res.id)

    def _extract_stack_resources(self, context, stack):
        stack_id = stack['id']
        properties = {}
        timeout_mins = stack['timeout_mins']
        if timeout_mins:
            properties['timeout'] = timeout_mins
        template = self.heat_api.get_template(context, stack_id)
        parameters = template.get('parameters')
        if parameters and parameters.get('OS::stack_id'):
            parameters.pop('OS::stack_id')
        if parameters and parameters.get('OS::project_id'):
            parameters.pop('OS::project_id')
        properties['parameters'] = parameters
        properties['disable_rollback'] = stack['disable_rollback']
        properties['stack_name'] = stack['stack_name']
        resource_type = "OS::Heat::Stack"
        resource_name = 'stack_%d' % self._get_resource_num(resource_type)
        stack_res = res.Resource(resource_name, resource_type,
                                 stack_id, properties=properties)
        stack_dep = res.ResourceDependency(stack_id,
                                           resource_name,
                                           stack['stack_name'],
                                           resource_type)
        sub_reses, dependencies_reses = self._extract_son_resources(
            context, stack_id, resource_name)
        for resource in sub_reses:
            stack_dep.add_dependency(resource.id, resource.name,
                                     resource.properties.get('name', ''),
                                     resource.type)
        template_skeleton = '''
            heat_template_version: '2013-05-23'
            description: Generated template
            parameters:
            resources:
            '''
        template = yaml.load(template_skeleton)
        template['resources'] = {}
        template['parameters'] = {}
        for r_resource in dependencies_reses:
            if r_resource in sub_reses:
                if r_resource.type not in handle_resource_types:
                    r_name = r_resource.name.split('.', 1)[-1]
                    r_resource.name = r_name
                template['resources'].update(r_resource.template_resource)
                template['parameters'].update(r_resource.template_parameter)
        for key, value in parameters.items():
            if key not in template['parameters'].keys():
                template['parameters'][key] = value
        stack_res.add_property('template', json.dumps(template))
        self._collected_resources[stack_id] = stack_res
        self._collected_dependencies[stack_id] = stack_dep
        return sub_reses

    def _extract_son_resources(self, context, stack_id, stack_name):
        sub_res_list = self._list_sub_resources(context, stack_id)
        template = self.heat_api.get_template(context, stack_id)
        sub_reses = []
        dependencies_reses = []
        new_resources = self._collected_resources
        new_dependencies = self._collected_dependencies
        sub_res_ids = []
        for sub_res in sub_res_list:
            sub_res_ids.append(sub_res.physical_resource_id)
        for sub_res in sub_res_list:
            res_type = sub_res.resource_type
            physical_resource_id = sub_res.physical_resource_id
            resource_name = sub_res.resource_name
            if res_type == 'OS::Nova::Server':
                origin_resources = copy.deepcopy(new_resources)
                ir = InstanceResource(context,
                                      collected_resources=new_resources,
                                      collected_dependencies=new_dependencies)
                res_info = ir.extract_instances([physical_resource_id],
                                                stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in ir.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            ir.get_collected_resources().get(k))
                new_resources = ir.get_collected_resources()
                new_dependencies = ir.get_collected_dependencies()
            elif res_type == 'OS::Glance::Image':
                origin_resources = copy.deepcopy(new_resources)
                ir = InstanceResource(context,
                                      collected_resources=new_resources,
                                      collected_dependencies=new_dependencies)
                res_info = ir.extract_image(physical_resource_id,
                                            stack_name, sub_res_ids)
                sub_reses.append(res_info)
                for k in ir.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            ir.get_collected_resources().get(k))
                new_resources = ir.get_collected_resources()
                new_dependencies = ir.get_collected_dependencies()
            elif res_type == 'OS::Nova::Flavor':
                origin_resources = copy.deepcopy(new_resources)
                ir = InstanceResource(context,
                                      collected_resources=new_resources,
                                      collected_dependencies=new_dependencies)
                res_info = ir.extract_flavors([physical_resource_id],
                                              stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in ir.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            ir.get_collected_resources().get(k))
                new_resources = ir.get_collected_resources()
                new_dependencies = ir.get_collected_dependencies()
            elif res_type == 'OS::Nova::KeyPair':
                origin_resources = copy.deepcopy(new_resources)
                ir = InstanceResource(context,
                                      collected_resources=new_resources,
                                      collected_dependencies=new_dependencies)
                res_info = ir.extract_keypairs([physical_resource_id],
                                               stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in ir.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            ir.get_collected_resources().get(k))
                new_resources = ir.get_collected_resources()
                new_dependencies = ir.get_collected_dependencies()
            elif res_type == 'OS::Cinder::Volume':
                origin_resources = copy.deepcopy(new_resources)
                vol = Volume(context,
                             collected_resources=new_resources,
                             collected_dependencies=new_dependencies)
                res_info = vol.extract_volume(physical_resource_id,
                                              stack_name, sub_res_ids)
                sub_reses.append(res_info)
                for k in vol.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            vol.get_collected_resources().get(k))
                new_resources = vol.get_collected_resources()
                new_dependencies = vol.get_collected_dependencies()
            elif res_type == 'OS::Cinder::VolumeType':
                origin_resources = copy.deepcopy(new_resources)
                vol = VolumeType(context,
                                 collected_resources=new_resources,
                                 collected_dependencies=new_dependencies)
                res_info = vol.extract_volume_types([physical_resource_id],
                                                    stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in vol.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            vol.get_collected_resources().get(k))
                new_resources = vol.get_collected_resources()
                new_dependencies = vol.get_collected_dependencies()
            elif res_type == 'OS::Neutron::Net':
                origin_resources = copy.deepcopy(new_resources)
                nt = NetworkResource(context,
                                     collected_resources=new_resources,
                                     collected_dependencies=new_dependencies)
                res_info = nt.extract_nets([physical_resource_id],
                                           stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in nt.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            nt.get_collected_resources().get(k))
                new_resources = nt.get_collected_resources()
                new_dependencies = nt.get_collected_dependencies()
            elif res_type == 'OS::Neutron::Subnet':
                origin_resources = copy.deepcopy(new_resources)
                nt = NetworkResource(context,
                                     collected_resources=new_resources,
                                     collected_dependencies=new_dependencies)
                res_info = nt.extract_subnets([physical_resource_id],
                                              stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in nt.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            nt.get_collected_resources().get(k))
                new_resources = nt.get_collected_resources()
                new_dependencies = nt.get_collected_dependencies()
            elif res_type == 'OS::Neutron::Port':
                origin_resources = copy.deepcopy(new_resources)
                nt = NetworkResource(context,
                                     collected_resources=new_resources,
                                     collected_dependencies=new_dependencies)
                res_info = nt.extract_ports([physical_resource_id],
                                            stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in nt.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            nt.get_collected_resources().get(k))
                new_resources = nt.get_collected_resources()
                new_dependencies = nt.get_collected_dependencies()
            elif res_type == 'OS::Neutron::Router':
                origin_resources = copy.deepcopy(new_resources)
                nt = NetworkResource(context,
                                     collected_resources=new_resources,
                                     collected_dependencies=new_dependencies)
                res_info = nt.extract_routers([physical_resource_id],
                                              stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in nt.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            nt.get_collected_resources().get(k))
                new_resources = nt.get_collected_resources()
                new_dependencies = nt.get_collected_dependencies()
            elif res_type == 'OS::Neutron::LoadBalancer':
                pass
            elif res_type.startswith('OS::Heat::') and \
                    res_type != 'OS::Heat::Stack':
                origin_resources = copy.deepcopy(new_resources)
                hr = HeatResource(context,
                                  collected_resources=new_resources,
                                  collected_dependencies=new_dependencies)
                res_info = hr.extract_resource(template, resource_name,
                                               res_type,
                                               physical_resource_id,
                                               stack_name, sub_res_ids)
                sub_reses.append(res_info)
                for k in hr.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            hr.get_collected_resources().get(k))
                new_resources = hr.get_collected_resources()
                new_dependencies = hr.get_collected_dependencies()
            elif res_type == 'OS::Neutron::FloatingIP':
                origin_resources = copy.deepcopy(new_resources)
                nt = NetworkResource(context,
                                     collected_resources=new_resources,
                                     collected_dependencies=new_dependencies)
                res_info = nt.extract_floatingips([physical_resource_id],
                                                  stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in nt.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            nt.get_collected_resources().get(k))
                new_resources = nt.get_collected_resources()
                new_dependencies = nt.get_collected_dependencies()
            elif res_type == 'OS::Neutron::SecurityGroup':
                origin_resources = copy.deepcopy(new_resources)
                st = SecGroup(context,
                              collected_resources=new_resources,
                              collected_dependencies=new_dependencies)
                res_info = st.extract_secgroups([physical_resource_id],
                                                stack_name, sub_res_ids)
                sub_reses.append(res_info[0])
                for k in st.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            st.get_collected_resources().get(k))
                new_resources = st.get_collected_resources()
                new_dependencies = st.get_collected_dependencies()
            elif res_type.startswith('file://'):
                son_res, son_dependencies_reses = self._extract_son_resources(
                    context, physical_resource_id, stack_name)
                sub_reses.extend(son_res)
                dependencies_reses.extend(son_dependencies_reses)
            elif res_type == "OS::Neutron::Pool":
                pass
            elif res_type not in handle_resource_types and \
                    not res_type.startswith('OS::Heat::'):
                origin_resources = copy.deepcopy(new_resources)
                hr = HeatResource(context,
                                  collected_resources=new_resources,
                                  collected_dependencies=new_dependencies)
                res_info = hr.extract_resource(template, resource_name,
                                               res_type,
                                               physical_resource_id,
                                               stack_name,
                                               sub_res_ids)
                sub_reses.append(res_info)
                for k in hr.get_collected_resources().keys():
                    if k not in origin_resources.keys():
                        dependencies_reses.append(
                            hr.get_collected_resources().get(k))
                new_resources = hr.get_collected_resources()
                new_dependencies = hr.get_collected_dependencies()
        self._collected_dependencies = new_dependencies
        self._collected_resources = new_resources
        return sub_reses, dependencies_reses

    def _list_sub_resources(self, context, stack_id):
        return self.heat_api.resources_list(context, stack_id)

    def is_file_type(self, t):
        return t and t.startswith('file://')

    def get_resources(self, res_list, t):
        """filter by resource type. """
        return [r for r in res_list if r.resource_type == t]
