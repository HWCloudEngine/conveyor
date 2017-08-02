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

JOB_STATUS = (
    SUCCESS, FAIL, RUNNING, INIT, WAITING, DELAY_SCHEDULED,
) = (
    'SUCCESS', 'FAIL', 'RUNNING', 'INIT', 'WAITING', 'DELAY_SCHEDULED',
)

RESOURCE_STATUS = (
    ACTIVE, PENDING_CREATE, ERROR,
) = (
    'ACTIVE', 'PENDING_CREATE', 'ERROR',
)


def retry_if_result_is_false(result):
    return result is False
