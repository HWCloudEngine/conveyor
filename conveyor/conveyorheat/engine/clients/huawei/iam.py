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

import requests

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine.clients import client_plugin
from conveyor.conveyorheat.engine.clients.huawei import exc
from conveyor.i18n import _LI

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils as json

LOG = logging.getLogger(__name__)


class IAMClientPlugin(client_plugin.ClientPlugin):

    service_types = [IAM] = ['iam']

    def _create(self):
        args = {
            'auth_url': (cfg.CONF.iam_authtoken.auth_uri or
                         self.context.auth_url),
            'token': self.context.auth_token,
            'tenant_id': self.context.tenant_id,
            'admin_username': cfg.CONF.iam_authtoken.admin_username,
            'admin_password': cfg.CONF.iam_authtoken.admin_password,
            'admin_domain': cfg.CONF.iam_authtoken.domain,
            'user_domain': self.context.user_domain,
            'ca_file': self._get_client_option('iam', 'ca_file'),
            'cert_file': self._get_client_option('iam', 'cert_file'),
            'key_file': self._get_client_option('iam', 'key_file'),
            'insecure': self._get_client_option('iam', 'insecure')
        }

        return Client('1', **args)

    def get_iam_url(self):
        iam_url = self._get_client_option('iam', 'url')
        if iam_url:
            tenant_id = self.context.tenant_id
            iam_url = iam_url % {'tenant_id': tenant_id}
        else:
            endpoint_type = self._get_client_option('iam',
                                                    'endpoint_type')
            iam_url = self.url_for(service_type='iam',
                                   endpoint_type=endpoint_type)
        return iam_url

    def is_not_found(self, ex):
        return isinstance(ex, exc.HTTPNotFound)

    def is_over_limit(self, ex):
        return isinstance(ex, exc.HTTPOverLimit)


class Client(object):
    def __init__(self, version, **kwargs):
        self.auth_url = kwargs.get('auth_url')
        self.token = kwargs.get('token')
        self.tenant_id = kwargs.get('tenant_id')
        self.admin_user = kwargs.get('admin_username')
        self.admin_pass = kwargs.get('admin_password')
        self.admin_domain_id = kwargs.get('admin_domain')
        self.user_domain_id = kwargs.get('user_domain')
        self.ca_file = kwargs.get('ca_file')
        self.cert_file = kwargs.get('cert_file')
        self.key_file = kwargs.get('key_file')

        self.auth = Auth(self)


class Auth(object):
    METHODS = (
        TOKEN, ASSUME_ROLE
    ) = (
        'token', 'assume_role'
    )

    def __init__(self, client):
        self.client = client

    def _get_token(self, creds, method='token', admin_token_info=None):
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        if method == self.ASSUME_ROLE:
            admin_token_id = self.admin_token()
            headers.update({
                "X-Auth-Token": admin_token_id
            })

        creds_json = json.dumps(creds)
        response = requests.post(self.client.auth_url + '/auth/tokens',
                                 data=creds_json,
                                 headers=headers,
                                 verify=False)

        token_id = None
        try:
            token_id = response.headers['X-Subject-Token']
            LOG.info(_LI("IAM authentication successful."))
        except (AttributeError, KeyError):
            LOG.info(_LI("IAM authentication failure."))
            raise exception.AuthorizationFailure()

        return token_id

    def _get_user_domain(self, admin_token_info=None):
        LOG.debug('Get user domain by project.')
        token_id = admin_token_info or self.admin_token()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            "X-Auth-Token": token_id
        }

        response = requests.get(
            self.client.auth_url + '/projects/%s' % self.client.tenant_id,
            headers=headers,
            verify=False)

        if response:
            try:
                project_info = response.json().get('project')
                domain_id = project_info.get('domain_id')
                LOG.debug('Get user domain (%s) by project (%s) success!'
                          % (domain_id, self.client.tenant_id))
                return domain_id
            except Exception:
                LOG.error('IAM get project error. Project id: %s' %
                          self.client.tenant_id)

    def admin_token(self):
        LOG.debug('Get IAM admin token.')
        creds = {
            'auth': {
                'identity': {
                    'methods': ['password'],
                    'password': {
                        'user': {
                            'name': cfg.CONF.iam_authtoken.admin_username,
                            'domain': {'name': cfg.CONF.iam_authtoken.domain},
                            'password': cfg.CONF.iam_authtoken.admin_password
                        }
                    }
                },
                'scope': {'domain': {'name': cfg.CONF.iam_authtoken.domain}}
            }
        }

        return self._get_token(creds)

    def assume_role(self):
        LOG.debug('Assume role by IAM.')
        admin_token_info = self.admin_token()
        creds = {
            "auth": {
                'identity': {
                    'methods': ['hw_assume_role'],
                    'hw_assume_role': {
                        'domain_id': self._get_user_domain(admin_token_info),
                        'xrole_name': 'op_service',
                        'restrict': {'roles': ['te_admin']}
                    }
                },
                'scope': {
                    'project': {
                        'id': self.client.tenant_id
                    }
                }
            }
        }

        return self._get_token(creds, self.ASSUME_ROLE)
