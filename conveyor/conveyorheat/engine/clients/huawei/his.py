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

from hisclient import exc
from hisclient.v2.client import Client as his_cli

from conveyor.conveyorheat.engine.clients import client_plugin
from conveyor.conveyorheat.engine import constraints


class HISClientPlugin(client_plugin.ClientPlugin):
    exceptions_module = exc
    service_types = [HIS] = ['his']

    def _create(self):
        endpoint = self._get_client_option('his', 'url')
        args = {
            'token': self.auth_token,
            'insecure': self._get_client_option('his', 'insecure'),
            'timeout': self._get_client_option('his', 'timeout'),
            'cacert': self._get_client_option('his', 'ca_file'),
            'cert': self._get_client_option('his', 'cert_file'),
            'key': self._get_client_option('his', 'key_file'),
            'ssl_compression': False
        }

        return his_cli(endpoint=endpoint, **args)


class HISConstraint(constraints.BaseCustomConstraint):
    resource_client_name = 'his'
    resource_getter_name = 'find_image_by_id'
