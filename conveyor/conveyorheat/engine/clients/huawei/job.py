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

import ssl

from hwcloud.common import exceptions as exc
from hwcloud.jobclient import client as jobc
from hwcloud import security

from conveyor.conveyorheat.engine.clients import client_plugin

security.VERIFY_SSL_CERT = False
ssl._create_default_https_context = ssl._create_unverified_context


class JobClientPlugin(client_plugin.ClientPlugin):

    exceptions_module = [exc]
    service_types = [JOB] = ['job']

    def _create(self):
        endpoint_type = self._get_client_option('job', 'endpoint_type')
        endpoint = self.url_for(service_type='job',
                                endpoint_type=endpoint_type)
        args = {
            'ex_force_auth_token': self.auth_token,
            'ex_force_base_url': endpoint,
            'ex_tenant_name': self.context.tenant_id
        }

        return jobc.HuaweiCloudNodeDriver(**args)

    def is_not_found(self, ex):
        return isinstance(ex, exc.NotFound)
