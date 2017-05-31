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

from oslo_utils import fileutils
from oslo_utils import uuidutils

from conveyor.compute import nova
from conveyor import context
from conveyor.conveyorheat.api import api as heat
from conveyor import exception
from conveyor.network import neutron
from conveyor.resource.driver import instances
from conveyor.resource import manager
from conveyor.resource import resource
from conveyor.tests import test
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


fake_plan_dict = {
    'plan_id': 'plan_id',
    'plan_name': 'plan_name',
    'plan_type': 'clone',
    'project_id': 'conveyor',
    'user_id': 'conveyor',
    'stack_id': '',
    'created_at': '',
    'updated_at': '',
    'expire_at': '',
    'deleted_at': '',
    'deleted': False,
    'task_status': '',
    'plan_status': '',
    'original_resources': {},
    'updated_resources': {},
    'original_dependencies': {},
    'updated_dependencies': {},
}

ori_res = {
    "subnet_0": {
        "name": "subnet_0",
        "parameters": {},
        "extra_properties": {
            "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183"
        },
        "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183",
        "type": "OS::Neutron::Subnet",
        "properties": {
            "name": "sub-conveyor",
            "enable_dhcp": True,
            "network_id": {
                "get_resource": "network_0"
            },
            "allocation_pools": [
                {
                    "start": "192.168.0.2",
                    "end": "192.168.0.254"
                }
            ],
            "gateway_ip": "192.168.0.1",
            "ip_version": 4,
            "cidr": "192.168.0.0/24"
        }
    },
    "port_0": {
        "name": "port_0",
        "parameters": {},
        "extra_properties": {
            "id": "bd289057-2e26-41dd-a319-8afbf7b687e8"
        },
        "id": "bd289057-2e26-41dd-a319-8afbf7b687e8",
        "type": "OS::Neutron::Port",
        "properties": {
            "name": "",
            "admin_state_up": True,
            "network_id": {
                "get_resource": "network_0"
            },
            "mac_address": "fa:16:3e:9d:35:e4",
            "fixed_ips": [
                {
                    "subnet_id": {
                        "get_resource": "subnet_0"
                    },
                    "ip_address": "192.168.0.3"
                }
            ],
            "security_groups": [
                {
                    "get_resource": "security_group_0"
                }
            ]
        }
    },
    "network_0": {
        "name": "network_0",
        "parameters": {},
        "extra_properties": {
            "id": "899a541a-4500-4605-a416-eb739501dd95"
        },
        "id": "899a541a-4500-4605-a416-eb739501dd95",
        "type": "OS::Neutron::Net",
        "properties": {
            "shared": False,
            "admin_state_up": True,
            "value_specs": {
                "router:external": False,
                "provider:network_type": "vxlan",
                "provider:segmentation_id": 9888
            },
            "name": "net-conveyor"
        }
    },
    "server_0": {
        "name": "server_0",
        "parameters": {
            "image_0": {
                "default": "be150fa9-84a9-4feb-a71c-7ba1a46dc544",
                "type": "string",
                "description": "Image to use to boot server or volume"
            }
        },
        "extra_properties": {
            "vm_state": "stopped",
            "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
            "power_state": 4
        },
        "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
        "type": "OS::Nova::Server",
        "properties": {
            "flavor": {
                "get_resource": "flavor_0"
            },
            "availability_zone": "az1.dc1",
            "networks": [
                {
                    "port": {
                        "get_resource": "port_0"
                    }
                }
            ],
            "image": {
                "get_param": "image_0"
            },
            "key_name": {
                "get_resource": "keypair_0"
            },
            "name": "ubuntu14.04"
        }
    },
    "security_group_0": {
        "name": "security_group_0",
        "parameters": {},
        "extra_properties": {
            "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5"
        },
        "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5",
        "type": "OS::Neutron::SecurityGroup",
        "properties": {
            "rules": [
                {
                    "ethertype": "IPv4",
                    "direction": "ingress",
                    "protocol": "icmp",
                    "description": "",
                    "remote_ip_prefix": "0.0.0.0/0"
                },
                {
                    "direction": "ingress",
                    "protocol": "tcp",
                    "description": "",
                    "ethertype": "IPv4",
                    "port_range_max": 22,
                    "port_range_min": 22,
                    "remote_ip_prefix": "0.0.0.0/0"
                },
                {
                    "ethertype": "IPv4",
                    "direction": "ingress",
                    "description": "",
                    "remote_mode": "remote_group_id"
                },
                {
                    "ethertype": "IPv4",
                    "direction": "egress",
                    "description": ""
                },
                {
                    "ethertype": "IPv6",
                    "direction": "ingress",
                    "description": "",
                    "remote_mode": "remote_group_id"
                },
                {
                    "ethertype": "IPv6",
                    "direction": "egress",
                    "description": ""
                }
            ],
            "description": "Default security group",
            "name": "_default"
        }
    },
    "flavor_0": {
        "name": "flavor_0",
        "parameters": {},
        "extra_properties": {
            "id": "6"
        },
        "id": "6",
        "type": "OS::Nova::Flavor",
        "properties": {
            "ram": 1024,
            "ephemeral": 0,
            "vcpus": 1,
            "rxtx_factor": 1,
            "is_public": True,
            "disk": 5
        }
    },
    "volume_0": {
        "name": "volume_0",
        "extra_properties": {
            "status": "available",
            "boot_index": 0,
            "id": "db06e9e7-8bd9-4139-835a-9276728b5dcd"
        },
        "id": "db06e9e7-8bd9-4139-835a-9276728b5dcd",
        "parameters": {
            "image_0": {
                "default": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                "type": "string",
                "description": "Image to use to boot server or volume"
            }
        },
        "type": "OS::Cinder::Volume",
        "properties": {
            "size": 20,
            "image": {
                "get_param": "image_0"
            },
            "availability_zone": "az01.dc1--fusionsphere",
            "name": "",
            "metadata": {
                "__hc_vol_id": "0ff07950-1e38-43bb-a001-851f41c31457",
                "readonly": "False",
                "__openstack_region_name": "az01.dc1--fusionsphere",
                "attached_mode": "rw"
            }
        }
    },
    "keypair_0": {
        "name": "keypair_0",
        "extra_properties": {
            "id": "test-keypair"
        },
        "id": "test-keypair",
        "parameters": {},
        "type": "OS::Nova::KeyPair",
        "properties": {
            "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDhkkslPA0xkVLtF5bCAoum+EEg6Dd8apUoNoDveSrlDIUR1hByo8E0Ijfw2G4xNIz6eStJCqXhtBQS+1Opx6A8wvlZe6qCANIo4s84zpLnYX8s2K0TCo0CUK2EdltGsBq4Fw8uyvHeRnsdgJ1Shucj2Vzq3UK7Wv0MHsXtSzssXVQAqa2iM7KnAjSXQ6tx3acdhire3V9wFx3xlZKFOJ383RSw7H4tPvNPXUGbmw3JkIs5zORXWMrMlQZ0TbVpPK6HG3fGRWVoqtkLMhxGGq/2rp7E31vBW+AoinN+fK9no2vjm83qRD49tQtLuG1LUMLP5P04KDeTC/CKutNsYi03 Generated-by-Nova\n",
            "name": "test-keypair"
        }
    }
}

ori_deps = {
    "subnet_0": {
        "name_in_template": "subnet_0",
        "dependencies": [
            "network_0"
        ],
        "type": "OS::Neutron::Subnet",
        "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183",
        "name": "sub-conveyor"
    },
    "port_0": {
        "name_in_template": "port_0",
        "dependencies": [
            "network_0",
            "subnet_0",
            "security_group_0"
        ],
        "type": "OS::Neutron::Port",
        "id": "bd289057-2e26-41dd-a319-8afbf7b687e8",
        "name": ""
    },
    "network_0": {
        "name_in_template": "network_0",
        "dependencies": [],
        "type": "OS::Neutron::Net",
        "id": "899a541a-4500-4605-a416-eb739501dd95",
        "name": "net-conveyor"
    },
    "server_0": {
        "name_in_template": "server_0",
        "dependencies": [
            "flavor_0",
            "port_0",
            "volume_0",
            "keypair_0"
        ],
        "type": "OS::Nova::Server",
        "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
        "name": "ubuntu14.04"
    },
    "security_group_0": {
        "name_in_template": "security_group_0",
        "dependencies": [],
        "type": "OS::Neutron::SecurityGroup",
        "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5",
        "name": "_default"
    },
    "flavor_0": {
        "name_in_template": "flavor_0",
        "dependencies": [],
        "type": "OS::Nova::Flavor",
        "id": "6",
        "name": "ubuntu"
    },
    "volume_0": {
        "name_in_template": "volume_0",
        "dependencies": [

        ],
        "type": "OS: : Cinder: : Volume",
        "id": "846f7bd9-56ca-403f-b805-f239c869e7e0",
        "name": "test2"
    },
    "keypair_0": {
        "name_in_template": "keypair_0",
        "dependencies": [],
        "type": "OS::Nova::KeyPair",
        "id": "test-keypair",
        "name": "test-keypair"
    }
}

updated_res = {
    "subnet_0": {
        "name": "subnet_0",
        "parameters": {},
        "extra_properties": {
            "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183"
        },
        "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183",
        "type": "OS::Neutron::Subnet",
        "properties": {
            "name": "sub-conveyor",
            "enable_dhcp": True,
            "network_id": {
                "get_resource": "network_0"
            },
            "allocation_pools": [
                {
                    "start": "192.168.0.2",
                    "end": "192.168.0.254"
                }
            ],
            "gateway_ip": "192.168.0.1",
            "ip_version": 4,
            "cidr": "192.168.0.0/24"
        }
    },
    "port_0": {
        "name": "port_0",
        "parameters": {},
        "extra_properties": {
            "id": "bd289057-2e26-41dd-a319-8afbf7b687e8"
        },
        "id": "bd289057-2e26-41dd-a319-8afbf7b687e8",
        "type": "OS::Neutron::Port",
        "properties": {
            "name": "",
            "admin_state_up": True,
            "network_id": {
                "get_resource": "network_0"
            },
            "mac_address": "fa:16:3e:9d:35:e4",
            "fixed_ips": [
                {
                    "subnet_id": {
                        "get_resource": "subnet_0"
                    },
                    "ip_address": "192.168.0.3"
                }
            ],
            "security_groups": [
                {
                    "get_resource": "security_group_0"
                }
            ]
        }
    },
    "network_0": {
        "name": "network_0",
        "parameters": {},
        "extra_properties": {
            "id": "899a541a-4500-4605-a416-eb739501dd95"
        },
        "id": "899a541a-4500-4605-a416-eb739501dd95",
        "type": "OS::Neutron::Net",
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
    },
    "server_0": {
        "name": "server_0",
        "parameters": {
            "image_0": {
                "default": "be150fa9-84a9-4feb-a71c-7ba1a46dc544",
                "type": "string",
                "description": "Image to use to boot server or volume"
            }
        },
        "extra_properties": {
            "vm_state": "stopped",
            "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
            "power_state": 4
        },
        "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
        "type": "OS::Nova::Server",
        "properties": {
            "name": "ubuntu14.04",
            "flavor": {
                "get_resource": "flavor_0"
            },
            "networks": [
                {
                    "port": {
                        "get_resource": "port_0"
                    }
                }
            ],
            "image": {
                "get_param": "image_0"
            },
            "key_name": {
                "get_resource": "keypair_0"
            },
            "availability_zone": "az1.dc1"
        }
    },
    "security_group_0": {
        "name": "security_group_0",
        "parameters": {},
        "extra_properties": {
            "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5"
        },
        "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5",
        "type": "OS::Neutron::SecurityGroup",
        "properties": {
            "rules": [
                {
                    "ethertype": "IPv4",
                    "direction": "ingress",
                    "protocol": "icmp",
                    "description": "",
                    "remote_ip_prefix": "0.0.0.0/0"
                },
                {
                    "direction": "ingress",
                    "protocol": "tcp",
                    "description": "",
                    "ethertype": "IPv4",
                    "port_range_max": 22,
                    "port_range_min": 22,
                    "remote_ip_prefix": "0.0.0.0/0"
                },
                {
                    "ethertype": "IPv4",
                    "direction": "ingress",
                    "description": "",
                    "remote_mode": "remote_group_id"
                },
                {
                    "ethertype": "IPv4",
                    "direction": "egress",
                    "description": ""
                },
                {
                    "ethertype": "IPv6",
                    "direction": "ingress",
                    "description": "",
                    "remote_mode": "remote_group_id"
                },
                {
                    "ethertype": "IPv6",
                    "direction": "egress",
                    "description": ""
                }
            ],
            "description": "Default security group",
            "name": "_default"
        }
    },
    "flavor_0": {
        "name": "flavor_0",
        "parameters": {},
        "extra_properties": {
            "id": "6"
        },
        "id": "6",
        "type": "OS::Nova::Flavor",
        "properties": {
            "ram": 1024,
            "ephemeral": 0,
            "vcpus": 1,
            "rxtx_factor": 1,
            "is_public": True,
            "disk": 5
        }
    },
    "volume_0": {
        "name": "volume_0",
        "extra_properties": {
            "status": "available",
            "boot_index": 0,
            "id": "db06e9e7-8bd9-4139-835a-9276728b5dcd"
        },
        "id": "db06e9e7-8bd9-4139-835a-9276728b5dcd",
        "parameters": {
            "image_0": {
                "default": "19a7e4c8-baa5-442a-859e-7e968dc8b189",
                "type": "string",
                "description": "Image to use to boot server or volume"
            }
        },
        "type": "OS::Cinder::Volume",
        "properties": {
            "size": 20,
            "image": {
                "get_param": "image_0"
            },
            "availability_zone": "az01.dc1--fusionsphere",
            "name": "",
            "metadata": {
                "__hc_vol_id": "0ff07950-1e38-43bb-a001-851f41c31457",
                "readonly": "False",
                "__openstack_region_name": "az01.dc1--fusionsphere",
                "attached_mode": "rw"
            }
        },
        "keypair_0": {
            "name": "keypair_0",
            "extra_properties": {
                "id": "test-keypair"
            },
            "id": "test-keypair",
            "parameters": {},
            "type": "OS::Nova::KeyPair",
            "properties": {
                "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDhkkslPA0xkVLtF5bCAoum+EEg6Dd8apUoNoDveSrlDIUR1hByo8E0Ijfw2G4xNIz6eStJCqXhtBQS+1Opx6A8wvlZe6qCANIo4s84zpLnYX8s2K0TCo0CUK2EdltGsBq4Fw8uyvHeRnsdgJ1Shucj2Vzq3UK7Wv0MHsXtSzssXVQAqa2iM7KnAjSXQ6tx3acdhire3V9wFx3xlZKFOJ383RSw7H4tPvNPXUGbmw3JkIs5zORXWMrMlQZ0TbVpPK6HG3fGRWVoqtkLMhxGGq/2rp7E31vBW+AoinN+fK9no2vjm83qRD49tQtLuG1LUMLP5P04KDeTC/CKutNsYi03 Generated-by-Nova\n",
                "name": "test-keypair"
            }
        }
    }
}

updated_deps = {
    "subnet_0": {
        "name_in_template": "subnet_0",
        "dependencies": [
            "network_0"
        ],
        "type": "OS::Neutron::Subnet",
        "id": "991b9dc0-e82a-4d77-badc-1e1ed165f183",
        "name": "sub-conveyor"
    },
    "port_0": {
        "name_in_template": "port_0",
        "dependencies": [
            "network_0",
            "subnet_0",
            "security_group_0"
        ],
        "type": "OS::Neutron::Port",
        "id": "bd289057-2e26-41dd-a319-8afbf7b687e8",
        "name": ""
    },
    "network_0": {
        "name_in_template": "network_0",
        "dependencies": [],
        "type": "OS::Neutron::Net",
        "id": "899a541a-4500-4605-a416-eb739501dd95",
        "name": "net-conveyor"
    },
    "server_0": {
        "name_in_template": "server_0",
        "dependencies": [
            "flavor_0",
            "port_0",
            "volume_0",
            "keypair_0"
        ],
        "type": "OS::Nova::Server",
        "id": "03ff981e-f31f-4a6f-8b5d-4d08c9408e87",
        "name": "ubuntu14.04"
    },
    "security_group_0": {
        "name_in_template": "security_group_0",
        "dependencies": [],
        "type": "OS::Neutron::SecurityGroup",
        "id": "0aa21ff5-dadf-4869-bcca-55ebd63b8dd5",
        "name": "_default"
    },
    "flavor_0": {
        "name_in_template": "flavor_0",
        "dependencies": [],
        "type": "OS::Nova::Flavor",
        "id": "6",
        "name": "ubuntu"
    },
    "volume_0": {
        "name_in_template": "volume_0",
        "dependencies": [

        ],
        "type": "OS: : Cinder: : Volume",
        "id": "846f7bd9-56ca-403f-b805-f239c869e7e0",
        "name": "test2"
    },
    "keypair_0": {
        "name_in_template": "keypair_0",
        "dependencies": [],
        "type": "OS::Nova::KeyPair",
        "id": "test-keypair",
        "name": "test-keypair"
    }
}


def mock_fake_plan():
    fake_plan = copy.deepcopy(fake_plan_dict)
    fake_plan.update({
        'original_resources': copy.deepcopy(ori_res),
        'updated_resources': copy.deepcopy(ori_res),
        'original_dependencies': copy.deepcopy(ori_deps),
        'updated_dependencies': copy.deepcopy(ori_deps)
    })
    return fake_plan


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
        print result

    # @mock.patch.object(instances.InstanceResource, 'extract_instances',
    #                        mock_extract_instances)
    # @mock.patch.object(resource, 'save_plan_to_db')
    # def test_create_plan_with_plan_name(self, mock_save_plan):
    #     fake_plan_type = 'clone'
    #     fake_plan_name = 'fake-mame'
    #     fake_resources = [{'type': 'OS::Nova::Server', 'id': 'server0'}]
    #     result = self.resource_manager.create_plan(self.context,
    #                                                fake_plan_type,
    #                                                fake_resources)
    #     self.assertEqual('server0', result[0])
    #     pass

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

    def test_build_plan_by_template(self):
        # TODO
        pass

    def test_get_original_resource_detail_from_plan(self):
        fake_plan = mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            result = self.resource_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0')
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_updated_resource_detail_from_plan(self):
        fake_plan = mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            result = self.resource_manager.get_resource_detail_from_plan(
                self.context, fake_plan['plan_id'], 'server_0',
                is_original=False)
            self.assertEqual('server_0', result['name'])
            self.assertEqual('OS::Nova::Server', result['type'])

    def test_get_not_exist_resource_detail_from_plan(self):
        fake_plan = mock_fake_plan()
        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.assertRaises(
                exception.ResourceNotFound,
                self.resource_manager.get_resource_detail_from_plan,
                self.context, fake_plan['plan_id'], 'server_fake')

    def test_get_plan_by_id(self):
        fake_plan = mock_fake_plan()
        # fake_plan = resource.Plan(plan_id=fake_plan_id, plan_type='clone',
        #                           project_id='conveyor', user_id='conveyor',
        #                           original_resources={},
        #                           updated_resources={},
        #                           original_dependencies={},
        #                           updated_dependencies={})
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

    @mock.patch.object(manager.ResourceManager, 'get_plan_by_id')
    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(fileutils, 'delete_if_exists')
    @mock.patch.object(heat.API, 'clear_table')
    def test_delete_plan(self, mock_plan_get, mock_plan_update,
                         mock_file_delete, mock_clear_table):
        # TODO
        mock_plan_get.return_value = mock_fake_plan()
        self.resource_manager.delete_plan(self.context, 'fake-id')
        pass

    @mock.patch.object(manager.ResourceManager, 'get_plan_by_id')
    @mock.patch.object(resource, 'update_plan_to_db')
    @mock.patch.object(fileutils, 'delete_if_exists', side_effect=OSError)
    def test_delete_without_template_or_deps_file(self, mock_plan_get,
                                                  mock_plan_udpate,
                                                  mock_file_delete):
        mock_plan_get.return_value = mock_fake_plan()
        self.assertRaises(exception.PlanDeleteError,
                          self.resource_manager.delete_plan,
                          self.context, 'fake-id')

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
        fake_plan_id = fake_plan_dict['plan_id']
        fake_values = {
            'status': 'fake'
        }
        self.assertRaises(exception.PlanUpdateError,
                          self.resource_manager.update_plan,
                          self.context,
                          fake_plan_id, fake_values)

    @mock.patch.object(resource, 'read_plan_from_db',
                       return_value=(fake_plan_dict,
                                     resource.Plan.from_dict(fake_plan_dict)))
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan(self, mock_plan_get, mock_update_plan):
        fake_plan_id = fake_plan_dict['plan_id']
        fake_values = {
            'task_status': 'finished',
            'plan_status': 'finished',
        }
        self.resource_manager.update_plan(self.context, fake_plan_id,
                                          fake_values)

    @mock.patch.object(resource, 'read_plan_from_db',
                       return_value=(fake_plan_dict,
                                     resource.Plan.from_dict(fake_plan_dict)))
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_add_volume_type(self, mock_plan_get,
                                                  mock_update_plan):
        fake_plan_id = fake_plan_dict['plan_id']
        fake_resources = [{
            'action': 'add',
            'resource_id': 'vol-type-01',
            'resource_type': 'OS::Cinder::VolumeType'
        }]
        self.resource_manager.update_plan_resources(
            self.context, fake_plan_id, resources=fake_resources)
        mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'read_plan_from_db',
                       return_value=(fake_plan_dict,
                                     resource.Plan.from_dict(
                                         fake_plan_dict)))
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_add_qos(self, mock_plan_get,
                                          mock_update_plan):
        fake_plan_id = fake_plan_dict['plan_id']
        fake_resources = [{
            'action': 'add',
            'resource_id': 'qos-01',
            'resource_type': 'OS::Cinder::Qos'
        }]
        self.resource_manager.update_plan_resources(
            self.context, fake_plan_id, resources=fake_resources)
        mock_update_plan.assert_called_once()

    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_delete_res(self, mock_update_plan):
        fake_plan = mock_fake_plan()

        fake_resources = [{
            'action': 'delete',
            'resource_id': 'volume_0',
            'resource_type': 'OS::Cinder::Volume'
        }]

        with mock.patch.object(
                resource, 'read_plan_from_db',
                return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
            self.resource_manager.update_plan_resources(
                self.context, fake_plan['plan_id'], resources=fake_resources)
            mock_update_plan.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_server(self, mock_get_res_type,
                                                    mock_update_plan):
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_keypair(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(nova.API, 'get_keypair')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_changing_keypair(
            self, mock_get_res_type, mock_keypair, mock_update_plan):
        mock_keypair.return_value = {
            'id': 'new-id',
            'name': 'new-keypair',
            'public_key': '12312313'
        }
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_secgroup(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(neutron.API, 'get_security_group')
    @mock.patch.object(resource, 'update_plan_to_db')
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
        fake_plan = mock_fake_plan()
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
        fake_plan = mock_fake_plan()
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

    # @mock.patch.object(heat.API, 'get_resource_type')
    # @mock.patch.object(networks.NetworkResource, 'extract_floatingips')
    # @mock.patch.object(resource, 'update_plan_to_db')
    # def test_update_plan_resource_by_editing_fip(
    #         self, mock_get_res_type, mock_fip, mock_update_plan):
    #     # NOTE: By changing the ori floating ip
    #     mock_fip.return_value = resource.Resource(
    #         'floatingip_1', 'OS::Neutron::FloatingIP', 'fake-new-fip-id')
    #     fake_plan = mock_fake_plan()
    #     fake_resources = [{
    #         'action': 'edit',
    #         'id': 'fake-new-fip-id',
    #         'resource_type': 'OS::Neutron::FloatingIP',
    #         'resource_id': 'floatingip_0'
    #     }]
    #     with mock.patch.object(
    #             resource, 'read_plan_from_db',
    #             return_value=(fake_plan, resource.Plan.from_dict(fake_plan))):
    #         self.resource_manager.update_plan_resources(
    #             self.context, fake_plan['plan_id'], resources=fake_resources)
    #         mock_update_plan.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_port(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(manager.ResourceManager, '_update_port_resource')
    def test_update_pan_resource_editing_port_with_error_fixedip(
            self, mock_get_res_type, mock_update_port):
        # 1. without fix_ips
        fake_plan = mock_fake_plan()
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
            mock_update_port.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(manager.ResourceManager, '_update_port_resource')
    def test_update_pan_resource_editing_port_without_valid_fixedips(
            self, mock_get_res_type, mock_update_port):
        # 1. without fix_ips
        fake_plan = mock_fake_plan()
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
            mock_update_port.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(manager.ResourceManager, '_update_port_resource')
    def test_update_pan_resource_editing_port_with_unequal_num(
            self, mock_get_res_type, mock_update_port):
        # 2. the number of updated fixed_ips is not equal to the ori number
        fake_plan = mock_fake_plan()
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
            mock_update_port.assert_called_once()

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_net(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = mock_fake_plan()
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

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(neutron.API, 'get_network')
    @mock.patch.object(resource, 'update_plan_to_db')
    def tset_update_plan_resource_by_changing_net(
            self, mock_get_res_type, mock_get_network, mock_update_plan):
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
        fake_plan = mock_fake_plan()
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

    def test_update_plan_resource_by_editing_subnet(self):
        pass

    @mock.patch.object(heat.API, 'get_resource_type')
    @mock.patch.object(resource, 'update_plan_to_db')
    def test_update_plan_resource_by_editing_volume(
            self, mock_get_res_type, mock_update_plan):
        fake_plan = mock_fake_plan()
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
        fake_plan = mock_fake_plan()
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
        fake_plan = mock_fake_plan()
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
        fake_plan = mock_fake_plan()
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