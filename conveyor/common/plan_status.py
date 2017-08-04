# Copyright 2011 OpenStack Foundation.
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

"""
status of a plan.
"""

PLAN_STATUS = (INITIATING, CREATING, AVAILABLE, CLONING, MIGRATING,
               FINISHED, DELETING, DELETED, ERROR_DELETING, EXPIRED, ERROR,
               RESOURCE_DELETING, RESOURCE_DELETING_FAILED) = (
               'initiating', 'creating', 'available', 'cloning', 'migrating',
               'finished', 'deleting', 'deleted',
               'error_deleting', 'expired', 'error',
               'cloned resources deleting',
               'cloned resources failed')


STATE_MAP = {
    'CREATE_IN_PROGRESS': 'cloning',
    'CREATE_COMPLETE': 'cloning',
    'DATA_TRANSFORMING': 'cloning',
    'DATA_TRANS_FINISHED': 'cloning',
    'CREATE_FAILED': 'error',
    'DATA_TRANS_FAILED': 'error',
    'FINISHED': 'finished',
}

MIGRATE_STATE_MAP = {
    'CREATE_IN_PROGRESS': 'migrating',
    'CREATE_COMPLETE': 'migrating',
    'DATA_TRANSFORMING': 'migrating',
    'DATA_TRANS_FINISHED': 'migrating',
    'CREATE_FAILED': 'error',
    'DATA_TRANS_FAILED': 'error',
    'MIGRATE_FINISH': 'finished'
}


RESOURCE_TYPES = ['OS::Nova::Server',
                  'OS::Cinder::Volume',
                  'OS::Neutron::Net',
                  'OS::Neutron::LoadBalancer',
                  'OS::Heat::Stack',
                  'OS::Neutron::FloatingIP',
                  'OS::Neutron::SecurityGroup',
                  'OS::Neutron::Pool',
                  'project',
                  'availability_zone']
