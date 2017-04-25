from conveyor.conveyorheat.engine.clients import client_plugin
from conveyor.conveyorheat.engine.clients.huawei.ces import alarm
from conveyor.conveyorheat.engine.clients.huawei.ces import metric_data
from conveyor.conveyorheat.engine.clients.huawei import exc
from conveyor.conveyorheat.engine.clients.huawei import httpclient

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class CESClientPlugin(client_plugin.ClientPlugin):

    service_types = [CES] = ['ces']

    def _create(self):
        args = {
            'auth_url': self.context.auth_url,
            'token': self.context.auth_token,
            'username': None,
            'password': None,
            'ca_file': self._get_client_option('ces', 'ca_file'),
            'cert_file': self._get_client_option('ces', 'cert_file'),
            'key_file': self._get_client_option('ces', 'key_file'),
            'insecure': self._get_client_option('ces', 'insecure')
        }

        endpoint = self.get_ces_url()
        # if self._get_client_option('ces', 'url'):
        #     # assume that the heat API URL is manually configured because
        #     # it is not in the keystone catalog, so include the credentials
        #     # for the standalone auth_password middleware
        #     args['username'] = self.context.username
        #     args['password'] = self.context.password

        return Client('1', endpoint, **args)

    def get_ces_url(self):
        ces_url = self._get_client_option('ces', 'url')
        if ces_url:
            tenant_id = self.context.tenant_id
            ces_url = ces_url % {'tenant_id': tenant_id}
        else:
            endpoint_type = self._get_client_option('ces', 'endpoint_type')
            ces_url = self.url_for(service_type='ces',
                                   endpoint_type=endpoint_type)
        return ces_url

    def is_not_found(self, ex):
        return isinstance(ex, exc.HTTPNotFound)

    def is_over_limit(self, ex):
        return isinstance(ex, exc.HTTPOverLimit)


class Client(object):
    def __init__(self, version, *args, **kwargs):
        self.http_client = httpclient._construct_http_client(*args, **kwargs)
        self.alarms = alarm.AlarmManager(self.http_client)
        self.metrics = metric_data.MetricDataManager(self.http_client)
