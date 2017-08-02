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

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine.clients import client_plugin
from conveyor.conveyorheat.engine import constraints

from hwcloud.common import exceptions as exc
from hwcloud.elbclient import client as elbc
from hwcloud import security

security.VERIFY_SSL_CERT = False
ssl._create_default_https_context = ssl._create_unverified_context


class ElbClientPlugin(client_plugin.ClientPlugin):

    exceptions_module = [exc]
    service_types = [ELBS] = ['elbs']

    def _create(self):
        endpoint_type = self._get_client_option('elb', 'endpoint_type')
        endpoint = self.url_for(service_type='elbs',
                                endpoint_type=endpoint_type)
        args = {
            'ex_force_auth_token': self.auth_token,
            'ex_force_base_url': endpoint,
            'ex_tenant_name': self.context.tenant_id
        }

        return elbc.HuaweiCloudNodeDriver(**args)

    def is_not_found(self, ex):
        return isinstance(ex, exc.NotFound)

    def get_loadbalancer_id(self, lb):
        try:
            return self.client().loadbalancer.get(lb).id
        except exception.NotFound:
            raise exception.EntityNotFound(entity='Loadbalancer',
                                           name=lb)

    def get_listener_id(self, ls):
        try:
            return self.client().listener.get(ls).id
        except exception.NotFound:
            raise exception.EntityNotFound(entity='Listener',
                                           name=ls)

    def get_certificate_id(self, cert_id):
        certs = self.client().certificate.list()['certificates']
        for cert in certs:
            if cert.id == cert_id:
                return cert.id
        raise exception.EntityNotFound(entity='Certificate',
                                       name=cert_id)


class LoadbalancerConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (exception.EntityNotFound,)

    def validate_with_client(self, client, value):
        client.client_plugin('elb').get_loadbalancer_id(value)


class ListenerConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (exception.EntityNotFound,)

    def validate_with_client(self, client, value):
        client.client_plugin('elb').get_listener_id(value)


class CertificateConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (exception.EntityNotFound,)

    def validate_with_client(self, client, value):
        client.client_plugin('elb').get_certificate_id(value)
