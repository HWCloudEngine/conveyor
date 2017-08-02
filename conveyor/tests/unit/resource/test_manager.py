# Copyright (c) 2017 Huawei, Inc.
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

import mock

from conveyor.compute import nova
from conveyor import context
from conveyor import exception
from conveyor.resource.driver import instances
from conveyor.resource.driver import networks
from conveyor.resource.driver import volumes
from conveyor.resource import manager
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object
from conveyor.volume import cinder


def mock_extract_instances(self, instance_ids=None):
    for instance_id in instance_ids:
        instance_resources = self._collected_resources.get(instance_id)
        if instance_resources:
            continue

        resource_type = "OS::Nova::Server"
        resource_name = "server_%d" % self._get_resource_num(resource_type)
        instance_resources = resource.Resource(resource_name,
                                               resource_type,
                                               instance_id, properties={})
        name = 'server_%s' % instance_id
        instance_dependencies = resource.ResourceDependency(instance_id,
                                                            name,
                                                            resource_name,
                                                            resource_type)

        self._collected_resources[instance_id] = instance_resources
        self._collected_dependencies[instance_id] = instance_dependencies


def mock_extract_networks(self, network_ids=None):
    for net_id in network_ids:
        net_resource = self._collected_resources.get(net_id)
        if net_resource:
            continue

        resource_type = "OS::Neutron::Net"
        resource_name = "server_%d" % self._get_resource_num(resource_type)
        net_resource = resource.Resource(resource_name,
                                         resource_type,
                                         net_id, properties={})
        name = 'volume_%s' % net_id
        net_dependency = resource.ResourceDependency(net_id,
                                                     name,
                                                     resource_name,
                                                     resource_type)

        self._collected_resources[net_id] = net_resource
        self._collected_dependencies[net_id] = net_dependency


def mock_extract_volumes(self, volume_ids=None):
    for volume_id in volume_ids:
        volume_resource = self._collected_resources.get(volume_id)
        if volume_resource:
            continue

        resource_type = "OS::Cinder::Volume"
        resource_name = "server_%d" % self._get_resource_num(resource_type)
        volume_resource = resource.Resource(resource_name,
                                            resource_type,
                                            volume_id, properties={})
        name = 'volume_%s' % volume_id
        instance_dependency = resource.ResourceDependency(volume_id,
                                                          name,
                                                          resource_name,
                                                          resource_type)

        self._collected_resources[volume_id] = volume_resource
        self._collected_dependencies[volume_id] = instance_dependency


class ResourceManagerTestCase(test.TestCase):

    def setUp(self):
        super(ResourceManagerTestCase, self).setUp()
        self.context = context.RequestContext(
            fake_object.fake_user_id,
            fake_object.fake_project_id,
            is_admin=False)
        self.resource_manager = manager.ResourceManager()

    def test_get_resourc_detail(self):
        fake_type = 'OS::Nova::Server'
        fake_id = 'fake-id'
        # Get only one matched resource
        with mock.patch.object(nova.API, 'get_server',
                               return_value={'id': 'server0'}):
            self.assertEqual({'id': 'server0'},
                             self.resource_manager.get_resource_detail(
                                 self.context, fake_type, fake_id))

        # Get list-matched resources
        with mock.patch.object(nova.API, 'get_server',
                               return_value=[{'id': 'server0'}]):
            self.assertEqual({'id': 'server0'},
                             self.resource_manager.get_resource_detail(
                                 self.context, fake_type, fake_id))
        # Get resource failed.
        with mock.patch.object(nova.API, 'get_server', side_effect=Exception):
            self.assertRaises(exception.ResourceNotFound,
                              self.resource_manager.get_resource_detail,
                              self.context, fake_type, fake_id)
        # Unsupported resource_type
        self.assertRaises(exception.ResourceTypeNotSupported,
                          self.resource_manager.get_resource_detail,
                          self.context, 'fake-type', 'fake-id')

    def test_get_resource_with_none_resource_type(self):
        fake_search_opts = {}
        self.assertRaises(exception.ResourceTypeNotFound,
                          self.resource_manager.get_resources,
                          self.context,
                          search_opts=fake_search_opts)

    def test_get_resource_with_unsupported_resource_type(self):
        fake_search_opts = {'type': 'fake-type'}
        self.assertRaises(exception.ResourceTypeNotSupported,
                          self.resource_manager.get_resources,
                          self.context,
                          search_opts=fake_search_opts)

    @mock.patch.object(nova.API, 'get_all_servers')
    def test_get_resources_for_server(self, mockt_all_servers):
        mockt_all_servers.return_value = [{'id': 'server0'}]
        fake_search_opts = {'type': 'OS::Nova::Server'}
        self.assertEqual([{'id': 'server0'}],
                         self.resource_manager.get_resources(
                             self.context, search_opts=fake_search_opts))

    @mock.patch.object(cinder.API, 'get_all')
    def test_get_resources_for_volume(self, mock_all_volumes):
        mock_all_volumes.return_value = [{'id': 'volume0'}]
        fake_search_opts = {'type': 'OS::Cinder::Volume'}
        self.assertEqual([{'id': 'volume0'}],
                         self.resource_manager.get_resources(
                             self.context, search_opts=fake_search_opts))

    @mock.patch.object(instances.InstanceResource, 'extract_instances',
                       mock_extract_instances)
    def test_build_resources_topo_from_server(self):
        # TODO(drngsl)
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        result = self.resource_manager.build_reources_topo(
            self.context, fake_resources)
        self.assertTrue(2 == len(result))
        ori_res = result[0]
        ori_dep = result[1]
        self.assertEqual(1, len(ori_res))
        self.assertEqual(1, len(ori_dep))

    @mock.patch.object(networks.NetworkResource, 'extract_networks_resource',
                       mock_extract_networks)
    def test_build_resources_topo_from_network(self):
        fake_resources = [{'type': 'OS::Neutron::Net', 'id': 'net0'}]
        result = self.resource_manager.build_reources_topo(
            self.context, fake_resources)
        self.assertTrue(2 == len(result))

    @mock.patch.object(volumes.Volume, 'extract_volumes',
                       mock_extract_volumes)
    def test_build_resources_topo_from_volume(self):
        fake_resources = [{'type': 'OS::Cinder::Volume', 'id': 'volume0'}]
        result = self.resource_manager.build_reources_topo(
            self.context, fake_resources)
        self.assertTrue(2 == len(result))

    def test_create_plan_without_valid_resource(self):
        fake_resources = [{}]
        self.assertRaises(exception.ResourceExtractFailed,
                          self.resource_manager.build_reources_topo,
                          self.context, fake_resources)

    def test_create_plan_with_unsupported_resource_type(self):
        fake_resources = [{'type': 'fake-type', 'id': 'fake-id'}]
        self.assertRaises(exception.ResourceTypeNotSupported,
                          self.resource_manager.build_reources_topo,
                          self.context, fake_resources)
