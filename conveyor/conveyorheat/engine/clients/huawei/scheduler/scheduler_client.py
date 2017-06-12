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

from conveyor.conveyorheat.engine.clients import client_plugin
from conveyor.conveyorheat.engine.clients.huawei import exc
from conveyor.conveyorheat.engine.clients.huawei import httpclient
from conveyor.conveyorheat.engine.clients.huawei.scheduler import scheduler

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class SchedulerClientPlugin(client_plugin.ClientPlugin):

    service_types = [SCHEDULER] = ['scheduler']

    def _create(self):
        args = {
            'auth_url': self.context.auth_url,
            'token': self.context.auth_token,
            'username': None,
            'password': None,
            'ca_file': self._get_client_option('scheduler', 'ca_file'),
            'cert_file': self._get_client_option('scheduler', 'cert_file'),
            'key_file': self._get_client_option('scheduler', 'key_file'),
            'insecure': self._get_client_option('scheduler', 'insecure')
        }

        endpoint = self.get_scheduler_url()

        return Client('1', endpoint, **args)

    def get_scheduler_url(self):
        ces_url = self._get_client_option('scheduler', 'url')
        if ces_url:
            tenant_id = self.context.tenant_id
            ces_url = ces_url % {'tenant_id': tenant_id}
        else:
            endpoint_type = self._get_client_option('scheduler',
                                                    'endpoint_type')
            ces_url = self.url_for(service_type='scheduler',
                                   endpoint_type=endpoint_type)
        return ces_url

    def is_not_found(self, ex):
        return isinstance(ex, exc.HTTPNotFound)

    def is_over_limit(self, ex):
        return isinstance(ex, exc.HTTPOverLimit)


class Client(object):
    def __init__(self, version, *args, **kwargs):
        self.http_client = httpclient._construct_http_client(*args, **kwargs)
        self.scheduler = scheduler.SchedulerManager(self.http_client)