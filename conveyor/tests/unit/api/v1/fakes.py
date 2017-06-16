# Copyright 2010 OpenStack Foundation
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

import datetime
import iso8601

from conveyor.tests.unit import fake_constants as fake

DEFAULT_PLAN_NAME = "displayname"
DEFAULT_PLAN_DESCRIPTION = "displaydesc"
DEFAULT_PLAN_TYPE = "clone"
DEFAULT_PLAN_STATUS = "available"
DEFAULT_PLAN_ID = fake.PLAN_ID
DEFAULT_AZ = "fakeaz"


def create_fake_plan(id, **kwargs):
    plan = {
        'id': id,
        'user_id': fake.USER_ID,
        'project_id': fake.PROJECT_ID,
        'availability_zone': DEFAULT_AZ,
        'plan_status': DEFAULT_PLAN_STATUS,
        'name': 'plan_test',
        'display_name': DEFAULT_PLAN_NAME,
        'display_description': DEFAULT_PLAN_DESCRIPTION,
        'updated_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                        tzinfo=iso8601.iso8601.Utc()),
        'created_at': datetime.datetime(1900, 1, 1, 1, 1, 1,
                                        tzinfo=iso8601.iso8601.Utc()),
        'plan_type': 'clone',
        'original_resource': '',
        'update_resources': ''
    }

    if kwargs.get('original_resource', None):
        plan['original_resource'] = kwargs.get('original_resource')
    if kwargs.get('update_resources', None):
        plan['update_resources'] = kwargs.get('update_resources')
    if kwargs.get('plan_status', None):
        plan['plan_status'] = kwargs.get('plan_status')
    return plan


def fake_clone_template():
    template = {'template':
                {'heat_template_version': '2013-05-23',
                 'description': 'clone template',
                 'plan_type': 'clone',
                 'parameters': {},
                 'resources': {'volume_0': {'type': 'OS::Cinder::Volume',
                               'properties': {'size': 1,
                                              'availability_zone': 'az01',
                                              'name': 'test-vol-8',
                                              'metadata': {'region': 'az01'}},
                               'extra_properties': {'status': 'in-use',
                                                    'is_deacidized': True,
                                                    'sys_dev_name': 'fake',
                                                    'id': 'fake'}}}}}
    return template


def fake_plan_api_get(self, context, id, **kwargs):
    plan = create_fake_plan(id, **kwargs)
    return plan
