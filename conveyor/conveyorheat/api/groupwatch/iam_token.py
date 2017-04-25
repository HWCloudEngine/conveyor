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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils as json
import requests
import webob

from conveyor.conveyorheat.api.aws import exception
from conveyor.conveyorheat.api.aws.exception import HeatAPIException
from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.common.i18n import _LI
from conveyor.conveyorheat.common import wsgi


LOG = logging.getLogger(__name__)


opts = [
    cfg.StrOpt('auth_uri',
               help=_("Authentication Endpoint URI.")),
    cfg.ListOpt('callback_allowed_uris',
                default=[]),
    cfg.StrOpt('admin_username',
               help='username for iam username'),
    cfg.StrOpt('admin_password',
               secret=True,
               help='password for iam user.'),
    cfg.StrOpt('domain',
               default='op_service',
               help='domain_id for iam user.'),
]
cfg.CONF.register_opts(opts, group='iam_authtoken')


class IAMToken(wsgi.Middleware):
    """Authenticate an request with IAM and convert to token."""

    def __init__(self, app, conf):
        self.conf = conf
        self.application = app

    def _conf_get(self, name):
        # try config from paste-deploy first
        if name in self.conf:
            return self.conf[name]
        else:
            return cfg.CONF.iam_authtoken[name]

    def _conf_get_auth_uri(self):
        auth_uri = self._conf_get('auth_uri')
        if auth_uri:
            return auth_uri
        else:
            raise HeatAPIException('miss iam auth uri')

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):

        if req.headers.get('X-Auth-Token'):
            LOG.info("found token in headers, continue")
            return self.application

        from_uri = req.remote_addr
        allowed_uris = self._conf_get('callback_allowed_uris')
        if allowed_uris and from_uri not in allowed_uris:
            raise HeatAPIException("")

        LOG.debug('get request from %s' % from_uri)
        return self._authorize(req, self._conf_get_auth_uri())

    def _authorize(self, req, auth_uri):
        LOG.info(_LI("Getting IAM credentials.."))

        user = self._conf_get('admin_username')
        pwd = self._conf_get('admin_password')
        domain = self._conf_get('domain')
        creds = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": user,
                            "domain": {
                                "name": domain
                            },
                            "password": pwd
                        }
                    }
                },
                "scope": {
                    "domain": {
                        "name": domain
                    }
                }
            }
        }
        creds_json = json.dumps(creds)
        headers = {'Content-Type': 'application/json'}
        LOG.info(_LI('Authenticating with %s'), auth_uri)
        response = requests.post(
            auth_uri.rstrip('/') + '/auth/tokens',
            data=creds_json,
            headers=headers,
            verify=False)
        try:
            token_id = response.headers['X-Subject-Token']
            LOG.info(_LI("IAM authentication successful."))
        except (AttributeError, KeyError):
            LOG.info(_LI("IAM authentication failure."))
            raise exception.HeatAccessDeniedError()

        # Authenticated!
        req.headers['X-Auth-Token'] = token_id

        return self.application


def IAMToken_filter_factory(global_conf, **local_conf):
    """Factory method for paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return IAMToken(app, conf)

    return filter
