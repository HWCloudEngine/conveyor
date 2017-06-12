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

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine import attributes
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.elb import elb_res_base
from conveyor.i18n import _


class Listener(elb_res_base.ElbBaseResource):
    """A resource for ELB Listener.

    Listener resource for Elastic Load Balance Service.
    """

    PROPERTIES = (
        NAME, DESCRIPTION, LB_ID, PROTOCOL, PORT,
        BACKEND_PROTOCOL, BACKEND_PORT, LB_ALGORITHM, SESSION_STICKY,
        STICKY_SESSION_TYPE, COOKIE_TIMEOUT, CERTIFICATE,
        TCP_TIMEOUT,
    ) = (
        'name', 'description', 'loadbalancer_id', 'protocol', 'port',
        'backend_protocol', 'backend_port', 'lb_algorithm', 'session_sticky',
        'sticky_session_type', 'cookie_timeout', 'certificate_id',
        'tcp_timeout',
    )

    _BACKEND_PROTOCOLS = (
        HTTP, TCP,
    ) = (
        'HTTP', 'TCP',
    )

    HTTPS = ('HTTPS')
    _PROTOCOLS = _BACKEND_PROTOCOLS + (HTTPS,)

    _LB_ALGORITHMS = (
        ROUND_ROBIN, LEAST_CONNECTIONS, SOURCE_IP,
    ) = (
        'roundrobin', 'leastconn', 'source',
    )

    ATTRIBUTES = (
        MEMBER_NUMBER_ATTR, STATUS_ATTR,
    ) = (
        'member_number', 'status',
    )
    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('The name of the listener.'),
            required=True,
            update_allowed=True,
            constraints=[
                constraints.AllowedPattern('^[0-9a-zA-Z-_]{1,64}$')]
        ),
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('The description of the listener.'),
            update_allowed=True,
            constraints=[constraints.AllowedPattern('^[^<>]{1,128}$')]
        ),
        LB_ID: properties.Schema(
            properties.Schema.STRING,
            _('The ID of load balancer associated.'),
            required=True,
            constraints=[
                constraints.CustomConstraint('elb.lb')
            ]
        ),
        PROTOCOL: properties.Schema(
            properties.Schema.STRING,
            _('The protocol of the listener.'),
            constraints=[
                constraints.AllowedValues(_PROTOCOLS)
            ],
            required=True
        ),
        BACKEND_PROTOCOL: properties.Schema(
            properties.Schema.STRING,
            _('The backend protocol of the listener.'),
            constraints=[
                constraints.AllowedValues(_BACKEND_PROTOCOLS)
            ],
            required=True
        ),
        PORT: properties.Schema(
            properties.Schema.INTEGER,
            _('The port of the listener.'),
            constraints=[
                constraints.Range(min=1, max=65535)
            ],
            required=True,
            update_allowed=True,
        ),
        BACKEND_PORT: properties.Schema(
            properties.Schema.INTEGER,
            _('The backend port of the listener.'),
            constraints=[
                constraints.Range(min=1, max=65535)
            ],
            required=True,
            update_allowed=True,
        ),
        LB_ALGORITHM: properties.Schema(
            properties.Schema.STRING,
            _('The algorithm used to distribute load.'),
            constraints=[
                constraints.AllowedValues(_LB_ALGORITHMS)
            ],
            required=True,
            update_allowed=True,
        ),
        SESSION_STICKY: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Whether to keep the session.'),
            update_allowed=True
        ),
        STICKY_SESSION_TYPE: properties.Schema(
            properties.Schema.STRING,
            _('The way of handing cookie.'),
            constraints=[
                constraints.AllowedValues(['insert'])
            ],
        ),
        COOKIE_TIMEOUT: properties.Schema(
            properties.Schema.INTEGER,
            _('The timeout of cookie in minute.'),
            constraints=[
                constraints.Range(min=1, max=1440)
            ],
            update_allowed=True
        ),
        CERTIFICATE: properties.Schema(
            properties.Schema.STRING,
            _('The ID of certificate.'),
            constraints=[
                constraints.CustomConstraint('elb.cert')
            ]
        ),
        TCP_TIMEOUT: properties.Schema(
            properties.Schema.INTEGER,
            _('The timeout of TCP session in minute.'),
            constraints=[
                constraints.Range(min=1, max=5)
            ],
            update_allowed=True
        ),
    }

    attributes_schema = {
        MEMBER_NUMBER_ATTR: attributes.Schema(
            _('The number of the members listened by this listener.'),
        ),
        STATUS_ATTR: attributes.Schema(
            _('The status of the listener.'),
        ),
    }

    def validate(self):
        super(Listener, self).validate()
        protocol = self.properties[self.PROTOCOL]
        session_sticky = self.properties[self.SESSION_STICKY]
        sticky_type = self.properties[self.STICKY_SESSION_TYPE]
        certificate = self.properties[self.CERTIFICATE]
        tcp_timeout = self.properties[self.TCP_TIMEOUT]

        if protocol == self.HTTP and session_sticky:
            if sticky_type != 'insert':
                msg = (_('Property %(sticky_type)s should be "insert" '
                         'when %(protocol)s is %(http)s and '
                         '%(session_sticky)s is enabled.') %
                       {'sticky_type': self.STICKY_SESSION_TYPE,
                        'protocol': self.PROTOCOL,
                        'http': self.HTTP,
                        'session_sticky': self.SESSION_STICKY})
                raise exception.StackValidationFailed(message=msg)
        if protocol == self.HTTPS:
            if not certificate:
                msg = (_('Property %(cert)s is required when %(protocol)s '
                         'is %(https)s') %
                       {'cert': self.CERTIFICATE,
                        'protocol': self.PROTOCOL,
                        'https': self.HTTPS})
                raise exception.StackValidationFailed(message=msg)
        if tcp_timeout and protocol != self.TCP:
            msg = (_('Property %(tcpt)s is valid when %(protocol)s '
                     'is %(tcp)s') %
                   {'tcpt': self.TCP_TIMEOUT,
                    'protocol': self.PROTOCOL,
                    'tcp': self.TCP})
            raise exception.StackValidationFailed(message=msg)

    def _resolve_attribute(self, name):
        if not self.resource_id:
            return

        ls = self.client().listener.get(self.resource_id)
        if name == self.MEMBER_NUMBER_ATTR:
            return ls.extra['member_number']
        if name == self.STATUS_ATTR:
            return ls.status

    def FnGetRefId(self):
        return self.resource_id

    def handle_create(self):
        props = self._prepare_properties(self.properties)
        ls = self.client().listener.create(**props)
        self.resource_id_set(ls.id)
        return ls.status

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            if self.COOKIE_TIMEOUT in prop_diff:
                if prop_diff[self.COOKIE_TIMEOUT] is None:
                    prop_diff.pop(self.COOKIE_TIMEOUT)
            if self.TCP_TIMEOUT in prop_diff:
                if prop_diff[self.TCP_TIMEOUT] is None:
                    prop_diff.pop(self.TCP_TIMEOUT)
            if self.SESSION_STICKY in prop_diff:
                if prop_diff[self.SESSION_STICKY] is None:
                    prop_diff.pop(self.SESSION_STICKY)
            self.client().listener.update(listener_id=self.resource_id,
                                          **prop_diff)

    def handle_delete(self):
        if not self.resource_id:
            return

        try:
            self.client().listener.delete(self.resource_id)
        except Exception as e:
            # here we don't use ignore_not_found, because elb raises:
            # BadRequest("Bad Request {'message': 'find listener failed',
            # 'code': 'ELB.6030'}",)
            if 'ELB.6030' in e.message:
                return
            raise

    def check_create_complete(self, ls_status):
        return self._check_active(ls_status)

    def needs_replace_failed(self):
        if not self.resource_id:
            return True

        with self.client_plugin().ignore_not_found:
            ls = self.client().listener.get(self.resource_id)
            return ls.status == 'ERROR'

        return True


def resource_mapping():
    return {
        'OSE::ELB::Listener': Listener,
    }
