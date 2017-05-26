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

import datetime

PROJECT_ID = '89afd400-b646-4bbc-b12b-c0a4d63e5bd3'
USER_ID = 'c853ca26-e8ea-4797-8a52-ee124a013d0e'
PLAN_ID = '1e5177e7-95e5-4a0f-b170-e45f4b469f6a'

FAKE_PLAN = {
    'plan_status': 'initiating',
    'project_id': 'd23b65e027f9461ebe900916c0412ade',
    'task_status': '',
    'user_id': '7e11a86b90a14dfd96d4142c6ea1e539',
    'original_resources': {
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
                'parameters': {
                    'OS::project_id': 'd23b65e027f9461ebe900916c0412ade',
                    'image': '19a7e4c8-baa5-442a-859e-7e968dc8b189',
                    'private_network_id':
                        '01329398-2050-4152-a034-c1b302e70619',
                    'flavor': '2',
                    'OS::stack_name': 'test-stack'
                },
                'template': '{"heat_template_version": "2013-05-23",'
                            ' "description": "A recorded server",'
                            ' "parameters": {"image": {"default": '
                            '"19a7e4c8-baa5-442a-859e-7e968dc8b189", '
                            '"type": "string"}, "private_network_id": '
                            '{"default": '
                            '"01329398-2050-4152-a034-c1b302e70619", '
                            '"type": "string"}, "flavor": {"default": "2",'
                            ' "type": "string"}}, "resources": {"server":'
                            ' {"type": "OS::Nova::Server", "properties": '
                            '{"flavor": {"get_param": "flavor"}, "networks":'
                            ' [{"network": {"get_param": '
                            '"private_network_id"}}], "image": {"get_param":'
                            ' "image"}, "availability_zone": '
                            '"az01.dc1--fusionsphere"}}}}'
            }
        }
    }, 'deleted': False, 'original_dependencies': {
        'stack_0': {
            'name_in_template': 'stack_0',
            'dependencies': [],
            'type': 'OS::Heat::Stack',
            'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe',
            'name': ''
        }
    }, 'plan_type': 'clone', 'updated_at': None,
    'stack_id': None, 'updated_resources': {
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
    }, 'updated_dependencies': {
        'stack_0': {
            'name_in_template': 'stack_0',
            'dependencies': [],
            'type': 'OS::Heat::Stack',
            'id': 'e76f3947-d76f-4dca-a5f4-5af9b57becfe',
            'name': ''
        }
    },
    'plan_id': 'b3bd135b-2465-48b0-958c-fbcf53d75727',
    'deleted_at': None, 'plan_name': 'b3bd135b-2465-48b0-958c-fbcf53d75727',
    'created_at': '2017-05-22 01:01:59.136550',
    'expire_at': '2017-05-22 02:01:59.136794'
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
    'heat_template_version': datetime.date(2013, 5, 23),
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
                    'mount_point':
                        '/opt/8e330083-d795-4cef-86de-f69a7dd9076a',
                    'gw_id': 'e1cd1e68-d250-4924-8ef2-fd34c72dc696',
                    'is_deacidized': True,
                    'sys_dev_name': '/dev/vdc',
                    'gw_url': '162.3.140.236:9998',
                    'id': '8e330083-d795-4cef-86de-f69a7dd9076a'
                }
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
