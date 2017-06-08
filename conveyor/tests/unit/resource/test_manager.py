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

import copy
import mock
import sys
import yaml

if sys.version_info >= (3, 0):
    import builtins as builtin
else:
    import __builtin__ as builtin

from oslo_utils import fileutils
from oslo_utils import uuidutils

from conveyor.compute import nova
from conveyor import context
from conveyor.conveyorheat.api import api as heat
from conveyor import exception
from conveyor import network
from conveyor.network import neutron
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
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.resource_manager = manager.ResourceManager()

    def tearDown(self):
        super(ResourceManagerTestCase, self).tearDown()
        manager._plans.clear()

    def test_get_resource_detail(self):
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

    def test_get_resources_with_none_resource_type(self):
        fake_search_opts = {}
        self.assertRaises(exception.ResourceTypeNotFound,
                          self.resource_manager.get_resources,
                          self.context,
                          search_opts=fake_search_opts)

    def test_get_resources_with_unsupported_resource_type(self):
        fake_search_opts = {'type': 'fake-type'}
        self.assertRaises(exception.ResourceTypeNotSupported,
                          self.resource_manager.get_resources,
                          self.context,
                          search_opts=fake_search_opts)

    @mock.patch.object(nova.API, 'get_all_servers',
                       return_value=[{'id': 'server0'}])
    def test_get_resources_for_server(self, mock_get_all_servers):
        fake_search_opts = {'type': 'OS::Nova::Server'}
        self.assertEqual([{'id': 'server0'}],
                         self.resource_manager.get_resources(
                             self.context, search_opts=fake_search_opts))

    @mock.patch.object(cinder.API, 'get_all', return_value=[{'id': 'volume0'}])
    def test_get_resources_for_volume(self, mock_get_all):
        fake_search_opts = {'type': 'OS::Cinder::Volume'}
        self.assertEqual([{'id': 'volume0'}],
                         self.resource_manager.get_resources(
                             self.context, search_opts=fake_search_opts))

    @mock.patch.object(instances.InstanceResource, 'extract_instances',
                       mock_extract_instances)
    @mock.patch.object(resource, 'save_plan_to_db')
    def test_create_plan_for_server(self, mock_save_plan):
        fake_plan_type = 'clone'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        result = self.resource_manager.create_plan(self.context,
                                                   fake_plan_type,
                                                   fake_resources)
        self.assertTrue(2 == len(result))
        new_plan = manager._plans[result[0]]
        self.assertEqual(result[0], new_plan.plan_name)
        mock_save_plan.assert_called_with(self.context, manager.plan_file_dir,
                                          new_plan.to_dict())

    @mock.patch.object(networks.NetworkResource, 'extract_networks_resource',
                       mock_extract_networks)
    @mock.patch.object(resource, 'save_plan_to_db')
    def test_create_plan_for_network(self, mock_save_plan):
        fake_plan_type = 'clone'
        fake_resources = [{'type': 'OS::Neutron::Net', 'id': 'net0'}]
        result = self.resource_manager.create_plan(self.context,
                                                   fake_plan_type,
                                                   fake_resources)
        self.assertTrue(2 == len(result))
        new_plan = manager._plans[result[0]]
        self.assertEqual(result[0], new_plan.plan_name)
        mock_save_plan.assert_called_with(self.context, manager.plan_file_dir,
                                          new_plan.to_dict())

    @mock.patch.object(volumes.Volume, 'extract_volumes',
                       mock_extract_volumes)
    @mock.patch.object(resource, 'save_plan_to_db')
    def test_create_plan_for_volume(self, mock_save_plan):
        fake_plan_type = 'clone'
        fake_resources = [{'type': 'OS::Cinder::Volume', 'id': 'volume0'}]
        result = self.resource_manager.create_plan(self.context,
                                                   fake_plan_type,
                                                   fake_resources)
        self.assertTrue(2 == len(result))
        new_plan = manager._plans[result[0]]
        self.assertEqual(result[0], new_plan.plan_name)
        mock_save_plan.assert_called_with(self.context, manager.plan_file_dir,
                                          new_plan.to_dict())

    @mock.patch.object(instances.InstanceResource, 'extract_instances',
                       mock_extract_instances)
    @mock.patch.object(resource, 'save_plan_to_db')
    def test_create_plan_with_plan_name(self, mock_save_plan):
        fake_plan_type = 'clone'
        fake_plan_name = 'fake-mame'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        result = self.resource_manager.create_plan(self.context,
                                                   fake_plan_type,
                                                   fake_resources,
                                                   fake_plan_name)
        self.assertTrue(2 == len(result))
        new_plan = manager._plans[result[0]]
        self.assertEqual(fake_plan_name, new_plan.plan_name)

    @mock.patch.object(instances.InstanceResource, 'extract_instances',
                       mock_extract_instances)
    @mock.patch.object(resource, 'save_plan_to_db')
    def test_create_migrate_plan(self, mock_save_plan):
        fake_plan_type = 'migrate'
        fake_plan_name = 'fake-mame'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        result = self.resource_manager.create_plan(self.context,
                                                   fake_plan_type,
                                                   fake_resources,
                                                   fake_plan_name)
        self.assertTrue(2 == len(result))
        new_plan = manager._plans[result[0]]
        self.assertFalse(len(new_plan.updated_resources))
        self.assertFalse(len(new_plan.updated_dependencies))
        mock_save_plan.assert_called_with(self.context, manager.plan_file_dir,
                                          new_plan.to_dict())

    def test_create_plan_without_valid_resource(self):
        fake_plan_type = 'clone'
        fake_resources = [{}]
        self.assertRaises(exception.ResourceExtractFailed,
                          self.resource_manager.create_plan,
                          self.context, fake_plan_type, fake_resources)

    def test_create_plan_with_unsupported_plan_type(self):
        fake_plan_type = 'fake-plan-type'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        self.assertRaises(exception.PlanTypeNotSupported,
                          self.resource_manager.create_plan,
                          self.context, fake_plan_type, fake_resources)

    def test_create_plan_with_unsupported_resource_type(self):
        fake_plan_type = 'clone'
        fake_resources = [{'type': 'fake-type', 'id': 'fake-id'}]
        self.assertRaises(exception.ResourceTypeNotSupported,
                          self.resource_manager.create_plan,
                          self.context, fake_plan_type, fake_resources)
        pass

    @mock.patch.object(yaml, 'safe_dump')
    @mock.patch.object(builtin, 'open')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_build_plan_by_template(self, mock_plan_update, mock_open,
                                    mock_yaml_dump):
        fake_template = copy.deepcopy(fake_object.fake_plan_template)
        fake_template = fake_template['template']
        fake_plan_dict = copy.deepcopy(fake_object.fake_plan_dict)
        fake_plan_dict.update({
            'expire_time': fake_template['expire_time'],
            'status': 'creating'
        })
        self.resource_manager.build_plan_by_template(self.context,
                                                     fake_plan_dict,
                                                     fake_template)
        mock_plan_update.assert_called_once()

    def test_get_original_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            result = self.resource_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0')
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_updated_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            result = self.resource_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0',
                is_original=False)
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_not_exist_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(
                exception.ResourceNotFound,
                self.resource_manager.get_resource_detail_from_plan,
                self.context, fake_plan['plan_id'], 'server_fake')

    def test_get_plan_by_id(self):
        fake_plan = fake_object.mock_fake_plan()
        fake_plan_id = fake_plan['plan_id']
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            result = self.resource_manager.get_plan_by_id(
                self.context, fake_plan_id)
            self.assertEqual(fake_plan_id, result.get('plan_id'))
            result2 = self.resource_manager.get_plan_by_id(
                self.context, fake_plan_id, detail=False)
            self.assertTrue('original_resources' not in result2)

    @mock.patch.object(heat.API, 'clear_table')
    @mock.patch.object(fileutils, 'delete_if_exists')
    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(manager.ResourceManager, 'get_plan_by_id')
    def test_delete_plan(self, mock_plan_get, mock_plan_update,
                         mock_file_delete, mock_clear_table):
        mock_plan_get.return_value = fake_object.mock_fake_plan()
        self.resource_manager.delete_plan(self.context, 'plan_id')
        mock_clear_table.assert_called_with(self.context, '', 'plan_id')

    def test_delete_unexisted_plan(self):
        # TODO(drngsl)
        # switch 'if not plan' is not reachable
        pass

    @mock.patch.object(fileutils, 'delete_if_exists', side_effect=OSError)
    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(manager.ResourceManager, 'get_plan_by_id')
    def test_delete_without_template_or_deps_file(self, mock_plan_get,
                                                  mock_plan_udpate,
                                                  mock_file_delete):
        mock_plan_get.return_value = fake_object.mock_fake_plan()
        self.assertRaises(exception.PlanDeleteError,
                          self.resource_manager.delete_plan,
                          self.context, 'fake-id')

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(fileutils, 'delete_if_exists')
    def test_force_delete_plan(self, mock_file_delete, mock_plan_udpate):
        self.resource_manager.force_delete_plan(self.context, 'fake-plan-id')
        mock_file_delete.assert_called()
        mock_plan_udpate.assert_called()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(fileutils, 'delete_if_exists', side_effect=OSError)
    def test_force_delete_plan_without_template_or_deps_file(self,
                                                             mock_file_delete,
                                                             mock_plan_update):
        self.assertRaises(exception.PlanDeleteError,
                          self.resource_manager.force_delete_plan,
                          self.context, 'fake-plan-id')

    def test_update_plan_with_not_allowed_prop(self):
        fake_plan_id = 'fake-id'
        fake_values = {
            'fake123': ''
        }
        self.assertRaises(exception.PlanUpdateError,
                          self.resource_manager.update_plan,
                          self.context,
                          fake_plan_id, fake_values)

    def test_update_plan_with_invalid_status(self):
        fake_plan_id = 'plan_id'
        fake_values = {
            'status': 'fake'
        }
        self.assertRaises(exception.PlanUpdateError,
                          self.resource_manager.update_plan,
                          self.context,
                          fake_plan_id, fake_values)

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_values = {
            'task_status': 'finished',
            'plan_status': 'finished',
        }
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan(self.context,
                                              fake_plan['plan_id'],
                                              fake_values)

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_adding_volume_type(self,
                                                        mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'add',
            'resource_id': 'vol-type-01',
            'resource_type': 'OS::Cinder::VolumeType'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_adding_qos(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'add',
            'resource_id': 'qos-01',
            'resource_type': 'OS::Cinder::Qos'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_deleting_res(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_plan['updated_resources']['volume_fake'] = {
            "name": "volume_fake",
            "extra_properties": {},
            "id": "fake-volume-id",
            "parameters": {},
            "type": "OS::Cinder::Volume",
            "properties": {}
        }
        fake_plan['updated_dependencies']['volume_fake'] = {
            "name_in_template": "volume_fake",
            "dependencies": [
            ],
            "type": "OS::Cinder::Volume",
            "id": "fake-volume-id",
            "name": "volume_fake"
        }
        fake_resources = [{
            'action': 'delete',
            'resource_id': 'volume_fake',
            'resource_type': 'OS::Cinder::Volume'
        }]

        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_deleting_failed(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'delete',
            'resource_id': 'volume_0',
            'resource_type': 'OS::Cinder::Volume'
        }]

        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_server(self, mock_get_res_type,
                                                    mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'user_data': 'L3Vzci9iaW4vYmFzaAplY2hv',
            'resource_type': 'OS::Nova::Server',
            'resource_id': 'server_0'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_keypair(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'public_key': 'new_public_key',
            'resource_type': 'OS::Nova::KeyPair',
            'resource_id': 'keypair_0'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(nova.API, 'get_keypair')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_changing_keypair(
            self, mock_get_res_type, mock_keypair, mock_update_plan):
        mock_keypair.return_value = {
            'id': 'new-id',
            'name': 'new-keypair',
            'public_key': '12312313'
        }
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'id': 'fake-new-keypair-id',
            'resource_type': 'OS::Nova::KeyPair',
            'resource_id': 'keypair_0'
        }]
        with mock.patch.object(
            resource, 'read_plan_from_db',
            return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_secgroup(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            u'rules': [{
                u'direction': u'ingress', u'protocol': u'icmp',
                u'description': u'', u'ethertype': u'IPv4',
                u'remote_ip_prefix': u'0.0.0.0/0'
            }],
            'action': 'edit',
            u'resource_type': u'OS::Neutron::SecurityGroup',
            u'resource_id': u'security_group_0'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(neutron.API, 'get_security_group')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_changing_secgroup(
            self, mock_get_res_type, mock_get_secgroup, mock_update_plan):
        mock_get_secgroup.return_value = {
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "description": "",
            "id": "f7a799da-00ed-412e-a790-be268c2a6a4a",
            "security_group_rules": [{
                "direction": "egress", "protocol": None, "description": "",
                "port_range_max": None,
                "id": "f6a2ef67-95c9-4fbf-9a86-167e359ce488",
                "remote_group_id": None,
                "remote_ip_prefix": None,
                "security_group_id": "f7a799da-00ed-412e-a790-be268c2a6a4a",
                "tenant_id": "d23b65e027f9461ebe900916c0412ade",
                "port_range_min": None, "ethertype": "IPv4"
            }, {
                "direction": "egress",
                "protocol": None, "description": "",
                "port_range_max": None,
                "id": "349e062d-73fb-434f-9a12-048c4e12ba77",
                "remote_group_id": None, "remote_ip_prefix": None,
                "security_group_id": "f7a799da-00ed-412e-a790-be268c2a6a4a",
                "tenant_id": "d23b65e027f9461ebe900916c0412ade",
                "port_range_min": None, "ethertype": "IPv6"
            }],
            "name": "test-secgroup"
        }
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            u'description': u'',
            u'resource_id': u'security_group_0',
            u'rules': [{
                u'remote_ip_prefix': u'0.0.0.0/0', u'direction': u'egress',
                u'description': u'', u'ethertype': u'IPv4'
            }, {
                u'remote_ip_prefix': u'::/0', u'direction': u'egress',
                u'description': u'', u'ethertype': u'IPv6'}
            ],
            'action': 'edit',
            u'id': u'f7a799da-00ed-412e-a790-be268c2a6a4a',
            u'resource_type': u'OS::Neutron::SecurityGroup',
            u'name': u'test-secgroup'}
        ]
        with mock.patch.object(
            resource, 'read_plan_from_db',
            return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_without_new_id_or_rules(
            self, mock_get_res_type):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            u'resource_type': u'OS::Neutron::SecurityGroup',
            u'resource_id': u'security_group_0'
        }]
        with mock.patch.object(
            resource, 'read_plan_from_db',
            return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(
                exception.PlanResourcesUpdateError,
                self.resource_manager.update_plan_resources,
                self.context, fake_plan['plan_id'], resources=fake_resources)

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(networks.NetworkResource, 'extract_floatingips')
    @mock.patch.object(neutron.API, 'get_floatingip')
    @mock.patch.object(network, 'API')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_fip(
            self, mock_get_res_type, mock_network_api, mock_get_fip,
            mock_extract_fip, mock_update_plan):
        # NOTE: By changing the ori floating ip
        mock_get_fip.return_value = {
            'floatingip_network_id': "new-floating-network-id",
            'router_id': None,
            "fixed_ip_address": None,
            'floating_ip_address': '192.230.1.37',
            'status': 'DOWN',
            'port_id': None,
            'id': 'new-floatingip-id'
        }
        mock_extract_fip.return_value = [resource.Resource(
            'floatingip_new', 'OS::Neutron::FloatingIP', 'fake-new-fip-id')]
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'id': 'fake-new-fip-id',
            'resource_type': 'OS::Neutron::FloatingIP',
            'resource_id': 'floatingip_1'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_port(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'resource_type': 'OS::Neutron::Port',
            'resource_id': 'port_0',
            'fixed_ips': [
                {
                    "subnet_id": {"get_resource": 'subnet_0'},
                    "ip_address": '192.168.0.10'
                }
            ]
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_pan_resource_editing_port_with_error_fixedip(
            self, mock_get_res_type, mock_plan_update):
        # 1. without fix_ips
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'resource_type': 'OS::Neutron::Port',
            'resource_id': 'port_0',
            'fixed_ips': [{
                "subnet_id": {"get_resource": 'subnet_0'},
                "ip_address": '192.168.10.10'
            }]
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_pan_resource_editing_port_without_valid_fixedips(
            self, mock_get_res_type, mock_plan_update):
        # 1. without fix_ips
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'resource_type': 'OS::Neutron::Port',
            'resource_id': 'port_0',
            'fixed_ips': []
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_pan_resource_editing_port_with_unequal_num(
            self, mock_get_res_type, mock_plan_update):
        # 2. the number of updated fixed_ips is not equal to the ori number
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'resource_type': 'OS::Neutron::Port',
            'resource_id': 'port_0',
            'fixed_ips': [
                {
                    "subnet_id": {"get_resource": 'subnet_0'},
                    "ip_address": '192.168.0.10'
                },
                {
                    "subnet_id": {"get_resource": 'subnet_1'},
                    "ip_address": '192.168.0.11'
                },
            ]
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_net(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'resource_type': 'OS::Neutron::Net',
            'resource_id': 'network_0',
            'name': 'new-net-name',
            'admin_state_up': False,
            'shared': True
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(networks.NetworkResource, 'extract_nets')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(network, 'API')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_changing_net(
            self, mock_get_res_type, mock_network_api,
            mock_get_network, mock_extract_nets, mock_update_plan):
        return
        mock_get_network.return_value = {
            "status": "ACTIVE", "router:external": False,
            "availability_zone_hints": [], "availability_zones": ["nova"],
            "qos_policy_id": None, "provider:physical_network": None,
            "subnets": ["46f7e0ad-b422-478e-8b56-9c2f9323c92b",
                        "ba5bc541-7d1d-4049-a889-090feb7ecb7f"],
            "name": "net-conveyor2", "created_at": "2017-05-26T01:14:32",
            "tags": [], "updated_at": "2017-05-26T01:14:33",
            "provider:network_type": "vxlan",
            "ipv6_address_scope": None,
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "mtu": 1450, "admin_state_up": True, "ipv4_address_scope": None,
            "shared": False, "provider:segmentation_id": 9867,
            "id": "1f1cd824-98d9-4e57-a90f-c68fbbc68bfc", "description": ""}
        mock_extract_nets.return_value = [
            resource.Resource('network_new',
                              'OS::Neutron::Net',
                              '1f1cd824-98d9-4e57-a90f-c68fbbc68bfc')]
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [
            {
                u'name': u'net-conveyor2',
                u'admin_state_up': True,
                u'resource_id': u'network_0',
                u'value_specs': {},
                'action': 'edit',
                u'shared': False,
                u'id': u'1f1cd824-98d9-4e57-a90f-c68fbbc68bfc',
                u'resource_type': u'OS::Neutron::Net'
            },
            {
                u'name': u'',
                u'admin_state_up': True,
                u'network_id': {u'get_resource': u'network_0'},
                u'resource_id': u'port_0',
                u'resource_type': u'OS::Neutron::Port',
                u'mac_address': u'fa:16:3e:9d:35:e4',
                'action': 'edit',
                u'fixed_ips': [
                     {
                         u'subnet_id': {u'get_resource': u'subnet_0'},
                         u'ip_address': u''
                     }
                ],
                u'security_groups': [{u'get_resource': u'security_group_0'}]
            },
            {
                u'name': u'subnet-conveyor2',
                u'enable_dhcp': True, u'resource_id': u'subnet_0',
                'action': 'edit',
                u'allocation_pools': [
                    {u'start': u'192.168.10.2', u'end': u'192.168.10.254'}
                ],
                u'gateway_ip': u'192.168.10.1',
                u'ip_version': 4,
                u'cidr': u'192.168.10.0/24',
                u'id': u'46f7e0ad-b422-478e-8b56-9c2f9323c92b',
                u'resource_type': u'OS::Neutron::Subnet'
            }
        ]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_subnet(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            "name": "sub-conveyor-change",
            "gateway_ip": "192.168.0.2",
            "no_gateway": True,
            "enable_dhcp": False,
            "resource_type": "OS::Neutron::Subnet",
            "resource_id": "subnet_0"}]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], fake_resources)
            mock_update_plan.assert_called_once()

    def test_update_plan_resource_by_changing_subnet(self):
        # NOTE: This test for update plan resource by select another subnet
        # from the original network.
        # The other if case: select another subnet from some other network
        # covers test case: test_update_plan_resource_by_changing_net, so here
        # ignore this case.
        pass

    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    def test_update_plan_resource_by_editing_volume(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Cinder::Volume',
            'resource_id': 'volume_0',
            'id': 'db06e9e7-8bd9-4139-835a-9276728b5dcd'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], fake_resources)
            mock_update_plan.assert_called_once()

    def test_update_plan_resource_by_changing_volume(self):
        pass

    def test_update_plan_resource_by_editing_volume_type(self):
        pass

    def test_update_plan_resource_with_unsupported_res_type(self):
        fake_plan = fake_object.mock_fake_plan()
        fake_plan['updated_resources']['network_fake'] = {
            "name": "network_0",
            "parameters": {},
            "extra_properties": {
                "id": "899a541a-4500-4605-a416-eb739501dd95"
            },
            "id": "899a541a-4500-4605-a416-eb739501dd95",
            "type": "fake",
            "properties": {
                "shared": False,
                "value_specs": {
                    "router:external": False,
                    "provider:segmentation_id": 9888,
                    "provider:network_type": "vxlan"
                },
                "name": "net-conveyor",
                "admin_state_up": True
            }
        }
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Neutron::Net',
            'resource_id': 'network_fake'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              fake_resources)

    def test_update_plan_resource_by_changing_volume_type(self):
        pass

    def test_update_plan_resource_with_unkown_resources(self):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'fake-res-type'
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              fake_resources)

    def test_update_plan_resource_with_unexisted_resource(self):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Nova::Server',
            'resource_id': uuidutils.generate_uuid()
        }]
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.resource_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              fake_resources)
