#    Copyright 2016 Red Hat, Inc.
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

PROJECT_ID = '89afd400-b646-4bbc-b12b-c0a4d63e5bd3'
USER_ID = 'c853ca26-e8ea-4797-8a52-ee124a013d0e'
PLAN_ID = '1e5177e7-95e5-4a0f-b170-e45f4b469f6a'

FAKE_PLAN = {
    'updated_resources': {
        'stack_0': {
            'name': 'stack_0',
            'parameters': {},
            'extra_properties': {
                'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe'
            },
            'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe',
            'type': 'OS::Heat::Stack',
            'properties': {
                'stack_name': 'test-stack',
                'disable_rollback': True,
                'template': '{"heat_template_version": "2013-05-23", '
                            '"description": "A recorded server", '
                            '"parameters": {"image": {"default": '
                            '"19a7e4c8-baa5-442a-859e-7e968dc8b189", '
                            '"type": "string"}, "private_network_id": '
                            '{"default": '
                            '"01329398-2050-4152-a034-c1b302e70619", '
                            '"type": "string"}, "flavor": {"default": "2", '
                            '"type": "string"}}, "resources": {"server": '
                            '{"type": "OS::Nova::Server", "properties": '
                            '{"flavor": {"get_param": "flavor"}, "networks": '
                            '[{"network": {"get_param": '
                            '"private_network_id"}}], "image": {"get_param":'
                            ' "image"}, "availability_zone": '
                            '"az01.dc1--fusionsphere"}}}}',
                'parameters': {
                    'OS::project_id': 'd23b65e027f9461ebe900916c0412ade',
                    'image': '19a7e4c8-baa5-442a-859e-7e968dc8b189',
                    'private_network_id':
                        '01329398-2050-4152-a034-c1b302e70619',
                    'flavor': '2',
                    'OS::stack_name': 'test-stack'
                }
            }
        }
    },
    'expire_at': '2017-05-22 02:01:59.136794'
}

FAKE_PLAN_VOLUME = {
    'plan_status': 'finished',
    'updated_resources': {
        'volume_0': {
            'name': 'volume_0',
            'parameters': {},
            'extra_properties': {
                'status': 'available',
                'gw_id': '62cecc16-e638-40df-9673-fb946f6d7440',
                'copy_data': False,
                'gw_url': '162.3.140.80:9998',
                'is_deacidized': True,
                'id': '82775f39-b529-49db-9518-69a6781c5f0b'
            },
            'id': '82775f39-b529-49db-9518-69a6781c5f0b',
            'type': 'OS::Cinder::Volume',
            'properties': {
                'metadata': {
                    '__openstack_region_name': 'az01.dc1--fusionsphere',
                    'tag:caa_volume_id':
                        '9f74ae8a-60e7-405c-a616-5729b277c19e',
                    'readonly': 'False',
                    'attached_mode': 'rw'
                },
                'availability_zone': 'az01.dc1--fusionsphere',
                'name': 'hml-blank-2',
                'size': 1
            }
        }
    },
    'expire_at': '2017-06-06 07:10:27.868833'
}

FAKE_PLAN_PORT = {
    'plan_status': 'finished',
    'updated_resources': {
        'subnet_0': {
            'name': 'subnet_0',
            'parameters': {},
            'extra_properties': {
                'id': 'ecc01e23-ed69-4c4a-a93c-6ab3d76e59d8'
            },
            'id': 'ecc01e23-ed69-4c4a-a93c-6ab3d76e59d8',
            'type': 'OS::Neutron::Subnet',
            'properties': {
                'name': 'test-subnet',
                'enable_dhcp': True,
                'network_id': {
                    'get_resource': 'network_0'
                },
                'allocation_pools': [{
                    'start': '197.168.16.2',
                    'end': '197.168.31.254'
                }],
                'gateway_ip': '197.168.16.1',
                'ip_version': 4,
                'cidr': '197.168.16.0/20'
            }
        },
        'port_0': {
            'name': 'port_0',
            'parameters': {},
            'extra_properties': {
                'id': 'fa46f85c-1e62-4d07-b01d-735f04da0d07'
            },
            'id': 'fa46f85c-1e62-4d07-b01d-735f04da0d07',
            'type': 'OS::Neutron::Port',
            'properties': {
                'name': '',
                'admin_state_up': True,
                'network_id': {
                    'get_resource': 'network_0'
                },
                'mac_address': 'fa:16:3e:ff:32:b9',
                'fixed_ips': [{
                    'subnet_id': {
                        'get_resource': 'subnet_0'
                    },
                    'ip_address': '197.168.16.154'
                }],
                'security_groups': [{
                    'get_resource': 'security_group_0'
                }]
            }
        },
        'network_0': {
            'name': 'network_0',
            'parameters': {},
            'extra_properties': {
                'id': '01329398-2050-4152-a034-c1b302e70619'
            },
            'id': '01329398-2050-4152-a034-c1b302e70619',
            'type': 'OS::Neutron::Net',
            'properties': {
                'shared': False,
                'value_specs': {
                    'router:external': False,
                    'provider:segmentation_id': 9957,
                    'provider:network_type': 'vxlan'
                },
                'name': 'test02',
                'admin_state_up': True
            }
        },
        'security_group_0': {
            'name': 'security_group_0',
            'parameters': {},
            'extra_properties': {
                'id': '6207c842-f8a1-4ce7-9931-acfbe7929df1'
            },
            'id': '6207c842-f8a1-4ce7-9931-acfbe7929df1',
            'type': 'OS::Neutron::SecurityGroup',
            'properties': {
                'rules': [{
                    'ethertype': 'IPv4',
                    'direction': 'ingress',
                    'description': '',
                    'remote_mode': 'remote_group_id'
                }, {
                    'ethertype': 'IPv4',
                    'direction': 'egress',
                    'description': ''
                }, {
                    'ethertype': 'IPv6',
                    'direction': 'ingress',
                    'description': '',
                    'remote_mode': 'remote_group_id'
                }, {
                    'ethertype': 'IPv6',
                    'direction': 'egress',
                    'description': ''
                }],
                'description': 'Default security group',
                'name': '_default'
            }
        }
    }, 'expire_at': '2017-06-06 09:07:55.499698'
}

FAKE_RETURN_RES = {
    'stack_0': {
        'name': 'stack_0',
        'parameters': {},
        'extra_properties': {
            'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe'
        },
        'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe',
        'type': 'OS::Heat::Stack',
        'properties': {
            'stack_name': 'test-stack',
            'disable_rollback': True,
            'template': '{"heat_template_version": "2013-05-23", '
                        '"description": "A recorded server", '
                        '"parameters": {"image": {"default": '
                        '"19a7e4c8-baa5-442a-859e-7e968dc8b189", '
                        '"type": "string"}, "private_network_id": '
                        '{"default": '
                        '"01329398-2050-4152-a034-c1b302e70619", '
                        '"type": "string"}, "flavor": {"default": "2", '
                        '"type": "string"}}, "resources": {"server": '
                        '{"type": "OS::Nova::Server", "properties": '
                        '{"flavor": {"get_param": "flavor"}, "networks": '
                        '[{"network": {"get_param": '
                        '"private_network_id"}}], "image": {"get_param":'
                        ' "image"}, "availability_zone": '
                        '"az01.dc1--fusionsphere"}}}}',
            'parameters': {
                'OS::project_id': 'd23b65e027f9461ebe900916c0412ade',
                'image': '19a7e4c8-baa5-442a-859e-7e968dc8b189',
                'private_network_id': '01329398-2050-4152-a034-c1b302e70619',
                'flavor': '2',
                'OS::stack_name': 'test-stack'
            }
        }
    }
}

ORI_TEMPLATE = {
    'heat_template_version': '2013-05-23',
    'description': 'Generated template',
    'parameters': {},
    'expire_time': '2017-05-23 08:58:17.663434',
    'plan_type': 'clone',
    'resources': {
        'volume_0': {
            'type': 'OS::Cinder::Volume',
            'properties': {
                'availability_zone': 'az02.dc1',
                'metadata': {
                    'readonly': 'False'
                },
                'name': 'vol_02',
                'size': 1
            },
            'extra_properties': {
                'status': 'in-use',
                'guest_format': 'ext3',
                'mount_point': '/opt/8e330083-d795-4cef-86de-f69a7dd9076a',
                'gw_id': 'e1cd1e68-d250-4924-8ef2-fd34c72dc696',
                'is_deacidized': True,
                'sys_dev_name': '/dev/vdc',
                'gw_url': '162.3.140.236:9998',
                'id': '8e330083-d795-4cef-86de-f69a7dd9076a'
            }
        }
    }
}

UPDATED_TEMPLATE = {
    'plan_id': '6052d9db-0b54-4f45-b5fe-62a62ac938eb',
    'template': {
        'heat_template_version': '2013-05-23',
        'description': 'clone template',
        'parameters': {},
        'resources': {
            'volume_0': {
                'type': 'OS::Cinder::Volume',
                'properties': {
                    'size': 1,
                    'availability_zone': 'az02.dc1',
                    'name': 'vol_02',
                    'metadata': {
                        'readonly': 'False'
                    }
                },
                'extra_properties': {
                    'status': 'in-use',
                    'guest_format': 'ext3',
                    'copy_data': True,
                    'mount_point':
                        '/opt/8e330083-d795-4cef-86de-f69a7dd9076a',
                    'gw_id': 'e1cd1e68-d250-4924-8ef2-fd34c72dc696',
                    'is_deacidized': True,
                    'sys_dev_name': '/dev/vdc',
                    'gw_url': '162.3.140.236:9998',
                    'id': '8e330083-d795-4cef-86de-f69a7dd9076a'
                },
                'id': '8e330083-d795-4cef-86de-f69a7dd9076a'
            }
        }
    }
}

FAKE_INSTANCE_TEMPLATE = {
    'plan_id': '60908ea1-d04f-43e4-a85d-1c0c419ae5a2',
    'template': {
        'resources': {
            'server_0': {
                'type': 'OS::Nova::Server',
                'name': 'az01-test-1',
                'id': '2086ee4b-d6eb-4249-9c34-e45725f34105',
                'properties': {
                    'block_device_mapping_v2': [{
                        'boot_index': 0,
                        'volume_id': {
                            'get_resource': 'volume_1'
                        },
                        'device_name': '/dev/vda'
                    }],
                    'flavor': {
                        'get_param': 'flavor_0'
                    },
                    'availability_zone': 'az03.dc1--fusionsphere',
                    'networks': [{
                        'port': {
                            'get_resource': 'port_0'
                        }
                    }],
                    'name': 'az01-test-1'
                },
                'extra_properties': {
                    'vm_state': 'stopped',
                    'sys_clone': False,
                    'gw_id': '482b01e8-6702-4add-831b-2b66350d2b4d',
                    'gw_url': '162.3.140.94:9998',
                    'is_deacidized': True,
                    'power_state': 4,
                    'id': '2086ee4b-d6eb-4249-9c34-e45725f34105'
                }
            },
            'volume_1': {
                'type': 'OS::Cinder::Volume',
                'name': '',
                'properties': {
                    'size': 20,
                    'image': {
                        'get_param': 'image_0'
                    },
                    'availability_zone': 'az03.dc1--fusionsphere',
                    'name': '',
                    'metadata': {
                        '__hc_vol_id': 'e1dbc46b-ea55-481d-86bf-869c7c8a96fb',
                        'readonly': 'False',
                        '__openstack_region_name': 'az01.dc1--fusionsphere',
                        'attached_mode': 'rw'
                    }
                },
                'extra_properties': {
                    'status': 'in-use',
                    'boot_index': 0,
                    'sys_clone': False,
                    'copy_data': True,
                    'is_deacidized': True,
                    'gw_url': '162.3.140.94:9998',
                    'id': '41f0374d-630e-475f-af9e-3dc693e3347c'
                },
                'id': '41f0374d-630e-475f-af9e-3dc693e3347c'
            }
        }
    }
}

FAKE_STACK = {'stack': {'id': 'dd4a5239-2780-4104-aa46-8a8f3d2f717b'}}
FAKE_STACK_STATUS = {'stack': {'id': 'dd4a5239-2780-4104-aa46-8a8f3d2f717b'},
                     'stack_status': 'COMPLETE',
                     'stack_action': 'CREATE'}
FAKE_EVENT_LIST = {'resource_name': 'volume_0',
                   'resource_status': 'COMPLETE'}
FAKE_RESOURCE = \
    {'physical_resource_id': '8e330083-d795-4cef-86de-f69a7dd9076a'}
FAKE_UPDATED = {
    "volume_0": {
        "extra_properties": {
            "status": "available",
            "copy_data": True,
            "id": "57af2efb-1e69-43bf-b1cd-ed7d8fff6bce"
        },
        "parameters": {},
        "id": "57af2efb-1e69-43bf-b1cd-ed7d8fff6bce",
        "type": "OS::Cinder::Volume",
        "properties": {
            "metadata": {
                "__openstack_region_name": "az01.dc1--fusionsphere",
                "tag:caa_volume_id": "7d08d212-5150-4ff9-b741-0a98e6f1a8e0"
            },
            "availability_zone": "az01.dc1--fusionsphere",
            "name": "hml-test-vol-8",
            "size": 1
        },
        "name": "volume_0"
    }
}
