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

from oslo_utils import uuidutils

from conveyor.compute import nova
from conveyor import context
from conveyor.conveyorheat.api import api as heat
from conveyor.db import api as db_api
from conveyor import exception
from conveyor import network
from conveyor.network import neutron
from conveyor.objects import plan
from conveyor.plan import manager
from conveyor.resource import api as resource_api
from conveyor.resource.driver import networks
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.tests.unit.resource import fake_object


def mock_build_res_topo(cls, context, resources):
    ori_res = {}
    ori_deps = {}
    for res in resources:
        res_type = res.get('type')
        res_id = res.get('id')
        name = '%s-%s' % (res_type, res_id)
        name_in_tmpl = uuidutils.generate_uuid()
        ori_res[name_in_tmpl] = resource.Resource(name_in_tmpl,
                                                  res_type, res_id)
        ori_deps[name_in_tmpl] = resource.ResourceDependency(res_id,
                                                             name,
                                                             name_in_tmpl,
                                                             res_type)
    return ori_res, ori_deps


class ResourceManagerTestCase(test.TestCase):

    def setUp(self):
        super(ResourceManagerTestCase, self).setUp()
        self.context = context.RequestContext(
            fake_object.fake_user_id,
            fake_object.fake_project_id,
            is_admin=False)
        self.plan_manager = manager.PlanManager()

    @mock.patch.object(resource_api.ResourceAPI, 'build_reources_topo',
                       mock_build_res_topo)
    @mock.patch.object(plan, 'save_plan_to_db')
    def test_create_plan(self, mock_save_plan):
        fake_plan_type = 'clone'
        fake_plan_name = 'fake-mame'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        result = self.plan_manager.create_plan(self.context,
                                                fake_plan_type,
                                                fake_resources,
                                               plan_name=fake_plan_name)
        self.assertEqual(2, len(result))
        self.assertEqual(1, len(result[1]))
        mock_save_plan.assert_called_once()

    @mock.patch.object(resource_api.ResourceAPI, 'build_reources_topo',
                       mock_build_res_topo)
    def test_create_plan_with_unsupported_plan_type(self):
        fake_plan_type = 'fake-plan-type'
        fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
        self.assertRaises(exception.PlanTypeNotSupported,
                          self.plan_manager.create_plan,
                          self.context, fake_plan_type, fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
    def test_build_plan_by_template(self, mock_plan_update):
        fake_template = copy.deepcopy(fake_object.fake_plan_template)
        fake_template = fake_template['template']
        fake_plan_dict = copy.deepcopy(fake_object.fake_plan_dict)
        fake_plan_dict.update({
            'expire_time': fake_template['expire_time'],
            'status': 'creating'
        })
        self.plan_manager.build_plan_by_template(self.context,
                                                 fake_plan_dict,
                                                 fake_template)
        mock_plan_update.assert_called_once()

    def test_get_original_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            result = self.plan_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0')
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_updated_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            result = self.plan_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0',
                is_original=False)
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_not_exist_resource_detail_from_plan(self):
        fake_plan = fake_object.mock_fake_plan()
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.assertRaises(
                exception.ResourceNotFound,
                self.plan_manager.get_resource_detail_from_plan,
                self.context, fake_plan['plan_id'], 'server_fake')

    def test_get_plan_by_id(self):
        fake_plan = fake_object.mock_fake_plan()
        fake_plan_id = fake_plan['plan_id']
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            result = self.plan_manager.get_plan_by_id(
                self.context, fake_plan_id)
            self.assertEqual(fake_plan_id, result.get('plan_id'))
            result2 = self.plan_manager.get_plan_by_id(
                self.context, fake_plan_id, detail=False)
            self.assertTrue('original_resources' not in result2)

    @mock.patch.object(db_api, 'plan_delete')
    @mock.patch.object(db_api, 'plan_template_delete')
    @mock.patch.object(heat.API, 'clear_table')
    @mock.patch.object(plan, 'update_plan_to_db')
    @mock.patch.object(manager.PlanManager, 'get_plan_by_id')
    def test_delete_plan(self, mock_plan_get, mock_plan_update,
                         mock_clear_table, mock_plan_tmpl_del,
                         mock_plan_delete):
        fake_plan = fake_object.mock_fake_plan()
        mock_plan_get.return_value = fake_plan
        self.plan_manager.delete_plan(self.context, 'plan_id')
        mock_clear_table.assert_called_with(self.context, '', 'plan_id')
        mock_plan_delete.assert_called_with(self.context, fake_plan['plan_id'])

    @mock.patch.object(db_api, 'plan_delete')
    @mock.patch.object(db_api, 'plan_template_delete')
    @mock.patch.object(heat.API, 'clear_table')
    @mock.patch.object(plan, 'read_plan_from_db')
    def test_force_delete_plan(self, mock_plan_read, mock_clear_table,
                               mock_plan_tmpl_del, mock_plan_delete):
        fake_plan = fake_object.mock_fake_plan()
        mock_plan_read.return_value = fake_plan
        self.plan_manager.force_delete_plan(self.context, fake_plan['plan_id'])
        mock_plan_read.assert_called_with(self.context, fake_plan['plan_id'])
        mock_plan_delete.assert_called_with(self.context, fake_plan['plan_id'])

    @mock.patch.object(db_api, 'plan_delete')
    @mock.patch.object(db_api, 'plan_template_delete',
                       side_effect=exception.PlanNotFoundInDb)
    @mock.patch.object(heat.API, 'clear_table')
    @mock.patch.object(plan, 'read_plan_from_db')
    def test_force_delete_plan_without_tmpl(self, mock_plan_read,
                                            mock_clear_table,
                                            mock_plan_tmpl_del,
                                            mock_plan_delete):
        fake_plan = fake_object.mock_fake_plan()
        mock_plan_read.return_value = fake_plan
        self.plan_manager.force_delete_plan(self.context, fake_plan['plan_id'])
        mock_plan_read.assert_called_with(self.context, fake_plan['plan_id'])
        mock_plan_delete.assert_called_with(self.context, fake_plan['plan_id'])

    def test_update_plan_with_not_allowed_prop(self):
        fake_plan_id = 'fake-id'
        fake_values = {
            'fake123': ''
        }
        self.assertRaises(exception.PlanUpdateError,
                          self.plan_manager.update_plan,
                          self.context,
                          fake_plan_id, fake_values)

    def test_update_plan_with_invalid_status(self):
        fake_plan_id = 'plan_id'
        fake_values = {
            'status': 'fake'
        }
        self.assertRaises(exception.PlanUpdateError,
                          self.plan_manager.update_plan,
                          self.context,
                          fake_plan_id, fake_values)

    @mock.patch.object(plan, 'update_plan_to_db')
    def test_update_plan(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_values = {
            'task_status': 'finished',
            'plan_status': 'finished',
        }
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan(self.context,
                                              fake_plan['plan_id'],
                                              fake_values)

    @mock.patch.object(plan, 'update_plan_to_db')
    def test_update_plan_resource_by_adding_volume_type(self,
                                                        mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'add',
            'resource_id': 'vol-type-01',
            'resource_type': 'OS::Cinder::VolumeType'
        }]
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
    def test_update_plan_resource_by_adding_qos(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'add',
            'resource_id': 'qos-01',
            'resource_type': 'OS::Cinder::Qos'
        }]
        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
    def test_update_plan_resource_by_deleting_failed(self, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        fake_resources = [{
            'action': 'delete',
            'resource_id': 'volume_0',
            'resource_type': 'OS::Cinder::Volume'
        }]

        with mock.patch.object(
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.plan_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
            return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
            return_value=fake_plan):
            self.plan_manager.update_plan_resources(
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
                plan, 'read_plan_from_db',
            return_value=fake_plan):
            self.assertRaises(
                exception.PlanResourcesUpdateError,
                self.plan_manager.update_plan_resources,
                self.context, fake_plan['plan_id'], resources=fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.plan_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.plan_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.assertRaises(exception.PlanResourcesUpdateError,
                              self.plan_manager.update_plan_resources,
                              self.context,
                              fake_plan['plan_id'],
                              resources=fake_resources)

    @mock.patch.object(plan, 'update_plan_to_db')
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
                plan, 'read_plan_from_db',
                return_value=fake_plan):
            self.plan_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
    @mock.patch.object(networks.NetworkResource, 'extract_nets')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(network, 'API')
    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_by_changing_net(
            self, mock_read_plan, mock_get_res_type, mock_network_api,
            mock_get_network, mock_extract_nets, mock_update_plan):
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
        mock_read_plan.return_value = fake_plan
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
            }
        ]
        self.plan_manager.update_plan_resources(
            self.context, fake_plan['plan_id'], resources=fake_resources)
        mock_update_plan.assert_called_once()

    @mock.patch.object(plan, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_by_editing_subnet(
            self, mock_read_plan, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        mock_read_plan.return_value = fake_plan
        fake_resources = [{
            "name": "sub-conveyor-change",
            "gateway_ip": "192.168.0.2",
            "no_gateway": True,
            "enable_dhcp": False,
            "resource_type": "OS::Neutron::Subnet",
            "resource_id": "subnet_0"}]
        self.plan_manager.update_plan_resources(
            self.context, fake_plan['plan_id'], fake_resources)
        mock_update_plan.assert_called_once()

    def test_update_plan_resource_by_changing_subnet(self):
        # NOTE: This test for update plan resource by select another subnet
        # from the original network.
        # The other if case: select another subnet from some other network
        # covers test case: test_update_plan_resource_by_changing_net, so here
        # ignore this case.
        pass

    @mock.patch.object(plan, 'update_plan_to_db')
    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_by_editing_volume(
            self, mock_read_plan, mock_get_res_type, mock_update_plan):
        fake_plan = fake_object.mock_fake_plan()
        mock_read_plan.return_value = fake_plan
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Cinder::Volume',
            'resource_id': 'volume_0',
            'id': 'db06e9e7-8bd9-4139-835a-9276728b5dcd'
        }]
        self.plan_manager.update_plan_resources(
            self.context, fake_plan['plan_id'], fake_resources)
        mock_update_plan.assert_called_once()

    def test_update_plan_resource_by_changing_volume(self):
        pass

    def test_update_plan_resource_by_editing_volume_type(self):
        pass

    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_with_unsupported_res_type(self,
                                                            mock_read_plan):
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
        mock_read_plan.return_value = fake_plan
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Neutron::Net',
            'resource_id': 'network_fake'
        }]
        self.assertRaises(exception.PlanResourcesUpdateError,
                          self.plan_manager.update_plan_resources,
                          self.context,
                          fake_plan['plan_id'],
                          fake_resources)

    def test_update_plan_resource_by_changing_volume_type(self):
        pass

    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_with_unkown_resources(self, mock_read_plan):
        fake_plan = fake_object.mock_fake_plan()
        mock_read_plan.return_value = fake_plan
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'fake-res-type'
        }]
        self.assertRaises(exception.PlanResourcesUpdateError,
                          self.plan_manager.update_plan_resources,
                          self.context,
                          fake_plan['plan_id'],
                          fake_resources)

    @mock.patch.object(plan, 'read_plan_from_db')
    def test_update_plan_resource_with_unexisted_resource(self,
                                                          mock_read_plan):
        fake_plan = fake_object.mock_fake_plan()
        mock_read_plan.return_value = fake_plan
        fake_resources = [{
            'action': 'edit',
            'size': '30',
            'resource_type': 'OS::Nova::Server',
            'resource_id': uuidutils.generate_uuid()
        }]
        self.assertRaises(exception.PlanResourcesUpdateError,
                          self.plan_manager.update_plan_resources,
                          self.context,
                          fake_plan['plan_id'],
                          fake_resources)
