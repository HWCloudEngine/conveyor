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

fake_user_id = '01329398-2050-4152-a034-c1b302e70619'
fake_project_id = 'd23b65e027f9461ebe900916c0412ade'

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
            "public_key": "ssh-rsa AAAAB303 Generated-by-Nova\n",
            "name": "test-keypair"
        }
    },
    "floatingip_1": {
        "name": "floatingip_1",
        "extra_properties": {
            "id": "ef3e57c1-9caa-48ce-a078-40e2829d3ec4"
        },
        "id": "ef3e57c1-9caa-48ce-a078-40e2829d3ec4",
        "parameters": {},
        "type": "OS::Neutron::FloatingIP",
        "properties": {
            "floating_network_id": {
                "get_resource": "network_1"
            }
        }
    },
    "network_1": {
        "name": "network_0",
        "extra_properties": {
            "id": "5ec3b971-2108-463c-a772-ac308e75b91a"
        },
        "id": "5ec3b971-2108-463c-a772-ac308e75b91a",
        "parameters": {},
        "type": "OS::Neutron::Net",
        "properties": {
            "shared": False,
            "value_specs": {
                "router:external": True,
                "provider:segmentation_id": 231,
                "provider:physical_network": "physnet1",
                "provider:network_type": "vlan"
            },
            "name": "public-net",
            "admin_state_up": True
        }
    },
    "subnet_1": {
        "name": "subnet_1",
        "extra_properties": {
            "id": "b8581a5a-a6f1-47a8-9850-3c176e11eb45"
        },
        "id": "b8581a5a-a6f1-47a8-9850-3c176e11eb45",
        "parameters": {},
        "type": "OS::Neutron::Subnet",
        "properties": {
            "name": "",
            "enable_dhcp": True,
            "network_id": {
                "get_resource": "network_1"
            },
            "allocation_pools": [{
                "start": "192.230.1.30",
                "end": "192.230.1.40"
            }],
            "gateway_ip": "192.230.1.1",
            "ip_version": 4,
            "cidr": "192.230.1.0/24"
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
    },
    "subnet_1": {
        "name_in_template": "subnet_1",
        "dependencies": [
            "network_1"
        ],
        "type": "OS::Neutron::Subnet",
        "id": "b8581a5a-a6f1-47a8-9850-3c176e11eb45",
        "name": ""
    },
    "network_1": {
        "name_in_template": "network_1",
        "dependencies": [],
        "type": "OS::Neutron::Net",
        "id": "5ec3b971-2108-463c-a772-ac308e75b91a",
        "name": "public-net"
    },
    "floatingip_1": {
        "name_in_template": "floatingip_1",
        "dependencies": ["network_1"],
        "type": "OS::Neutron::FloatingIP",
        "id": "ef3e57c1-9caa-48ce-a078-40e2829d3ec4",
        "name": ""
    },
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


fake_plan_template = {
    "template": {
        "heat_template_version": "2013-05-23",
        "description": "Generated template",
        "plan_type": "clone",
        "expire_time": "2017-5-51 12:33:00",
        "parameter": {},
        "resources": {
            "volume_0": {
                "type": "OS::Cinder::Volume",
                "name": "test",
                "metadata": {},
                "availability_zone": "az01",
                "extra_properties": {
                    "status": "in-use",
                    "id": "123",
                    "copy_data": "True"
                }
            }
        }
    }
}

fake_net_dict = {
    "status": "ACTIVE",
    "subnets": [
        "f49b5787-ef10-4769-8b72-340c04decc92"
    ],
    "availability_zone_hints": [],
    "availability_zones": [],
    "name": "test02",
    "provider:physical_network": None,
    "admin_state_up": True,
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "created_at": "2017-03-27T01:54:49",
    "tags": [],
    "updated_at": "2017-03-27T01:54:49",
    "ipv6_address_scope": None,
    "description": "",
    "router:external": False,
    "provider:network_type": "vxlan",
    "ipv4_address_scope": None,
    "shared": False,
    "mtu": 1450,
    "id": "2c9f925b-ad53-4cc0-8e16-6e555e01773a",
    "provider:segmentation_id": 9957
}

fake_subnet_dict = {
    "description": "",
    "enable_dhcp": True,
    "network_id": "2c9f925b-ad53-4cc0-8e16-6e555e01773a",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "created_at": "2017-03-25T02:21:48",
    "dns_nameservers": [],
    "updated_at": "2017-03-25T02:21:48",
    "gateway_ip": "192.168.0.1",
    "ipv6_ra_mode": None,
    "allocation_pools": [
        {
            "start": "192.168.0.2",
            "end": "192.168.15.254"
        }
    ],
    "host_routes": [],
    "ip_version": 4,
    "ipv6_address_mode": None,
    "cidr": "192.168.0.0/20",
    "id": "f49b5787-ef10-4769-8b72-340c04decc92",
    "subnetpool_id": None,
    "name": "subnet-test"
}

fake_port_dict = {
    "status": "DOWN",
    "created_at": "2017-03-25T02:21:49",
    "binding:host_id": "",
    "description": "",
    "allowed_address_pairs": [],
    "admin_state_up": True,
    "network_id": "2c9f925b-ad53-4cc0-8e16-6e555e01773a",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "extra_dhcp_opts": [],
    "updated_at": "2017-03-25T02:21:49",
    "name": "",
    "binding:vif_type": "unbound",
    "device_owner": "network:dhcp",
    "mac_address": "fa:16:3e:39:a2:63",
    "binding:vif_details": {},
    "binding:profile": {},
    "binding:vnic_type": "normal",
    "fixed_ips": [{"subnet_id": "f49b5787-ef10-4769-8b72-340c04decc92",
                   "ip_address": "192.168.0.2"}],
    "id": "91d59727-23df-46cc-95d9-07cbb7d982f9",
    "security_groups": [],
    "device_id": ""
}

fake_secgroup_dict = {
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "description": "Default security group",
    "id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
    "security_group_rules": [
        {
            "direction": "egress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "061e23dd-78d8-47c3-bb6b-4a22f6e8de4e",
            "remote_group_id": None,
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv6"
        },
        {
            "direction": "ingress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "8c44bf1e-c28f-483a-96ed-8c95a5269c3c",
            "remote_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv4"
        },
        {
            "direction": "egress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "df56261d-c9e0-48ea-88a9-b14ec67209a4",
            "remote_group_id": None,
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv4"
        },
        {
            "direction": "ingress",
            "protocol": None,
            "description": "",
            "port_range_max": None,
            "id": "7957cff7-34e5-4a57-bb0c-cb299a145dd4",
            "remote_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "remote_ip_prefix": None,
            "security_group_id": "164c7126-ee4e-44e8-afb5-cc2f11225b30",
            "tenant_id": "d23b65e027f9461ebe900916c0412ade",
            "port_range_min": None,
            "ethertype": "IPv6"
        }
    ],
    "name": "default"
}

fake_fip_dict = {
    "router_id": None,
    "status": "DOWN",
    "description": "",
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "floating_network_id": "01329398-2050-4152-a034-c1b302e70619",
    "fixed_ip_address": None,
    "floating_ip_address": "192.230.1.3",
    "port_id": None,
    "id": "da1efe8d-b91c-475e-a095-e21df9af1a0d"
}

fake_router_dict = {
    "status": "ACTIVE",
    "external_gateway_info": {
        "network_id": "8dcd2896-f60c-4384-ad39-a8df2fabc0ce",
        "enable_snat": True,
        "external_fixed_ips": [
            {
                "subnet_id": "92565a39-f253-4186-81ac-b9f4201c37c1",
                "ip_address": "192.230.1.4"
            }
        ]
    },
    "availability_zone_hints": [],
    "availability_zones": [
        "nova"
    ],
    "description": "",
    "admin_state_up": True,
    "tenant_id": "d23b65e027f9461ebe900916c0412ade",
    "distributed": False,
    "routes": [],
    "ha": False,
    "id": "8e2941d7-f631-419f-bdaf-bd45615851b3",
    "name": "conveyor-router"
}
