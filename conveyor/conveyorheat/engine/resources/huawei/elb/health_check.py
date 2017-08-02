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
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.elb import elb_res_base
from conveyor.i18n import _


class HealthCheck(elb_res_base.ElbBaseResource):
    """A resource for ELB Health Check.

    Health Check resource for Elastic Load Balance Service.
    """

    PROPERTIES = (
        LISTENER_ID, PROTOCOL, URI,
        CONNECT_PORT, HEALTHY_THRESHOLD, UNHEALTHY_THRESHOLD,
        TIMEOUT, INTERVAL,
    ) = (
        'listener_id', 'healthcheck_protocol', 'healthcheck_uri',
        'healthcheck_connect_port', 'healthy_threshold', 'unhealthy_threshold',
        'healthcheck_timeout', 'healthcheck_interval',
    )

    _PROTOCOLS = (
        HTTP, TCP,
    ) = (
        'HTTP', 'TCP',
    )

    properties_schema = {
        LISTENER_ID: properties.Schema(
            properties.Schema.STRING,
            _('The ID of listener associated.'),
            required=True,
            constraints=[
                constraints.CustomConstraint('elb.ls')
            ]
        ),
        PROTOCOL: properties.Schema(
            properties.Schema.STRING,
            _('The protocol of the health check.'),
            constraints=[
                constraints.AllowedValues(_PROTOCOLS)
            ],
            update_allowed=True
        ),
        URI: properties.Schema(
            properties.Schema.STRING,
            _('The HTTP path used in the HTTP request to check a member '
              'health.'),
            constraints=[
                constraints.AllowedPattern('^[/][0-9a-zA-Z-/.%?#&]{0,79}$')
            ],
            update_allowed=True
        ),
        CONNECT_PORT: properties.Schema(
            properties.Schema.INTEGER,
            _('The port of the health check.'),
            constraints=[
                constraints.Range(min=1, max=65535)
            ],
            update_allowed=True
        ),
        HEALTHY_THRESHOLD: properties.Schema(
            properties.Schema.INTEGER,
            _('The number of the successful threshold before change the '
              'member status to healthy.'),
            constraints=[
                constraints.Range(min=1, max=10)
            ],
            update_allowed=True
        ),
        UNHEALTHY_THRESHOLD: properties.Schema(
            properties.Schema.INTEGER,
            _('The number of the failure threshold before change the '
              'member status to unhealthy.'),
            constraints=[
                constraints.Range(min=1, max=10)
            ],
            update_allowed=True
        ),
        TIMEOUT: properties.Schema(
            properties.Schema.INTEGER,
            _('The timeout of the health check in seconds.'),
            constraints=[
                constraints.Range(min=1, max=50)
            ],
            update_allowed=True
        ),
        INTERVAL: properties.Schema(
            properties.Schema.INTEGER,
            _('The interval between the health checks in seconds.'),
            constraints=[
                constraints.Range(min=1, max=5)
            ],
            update_allowed=True
        ),
    }

    def validate(self):
        super(HealthCheck, self).validate()
        protocol = self.properties[self.PROTOCOL]
        uri = self.properties[self.URI]

        if uri and protocol != self.HTTP:
            msg = (_('Property %(uri)s is valid if %(protocol)s '
                     'is %(http)s.') %
                   {'uri': self.URI,
                    'protocol': self.PROTOCOL,
                    'http': self.HTTP})
            raise exception.StackValidationFailed(message=msg)

    def handle_create(self):
        props = self._prepare_properties(self.properties)
        healthy_check = self.client().healthcheck.create(**props)
        self.resource_id_set(healthy_check.id)

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            self.client().healthcheck.update(healthcheck_id=self.resource_id,
                                             **prop_diff)

    def handle_delete(self):
        if not self.resource_id:
            return
        try:
            self.client().healthcheck.delete(self.resource_id)
        except Exception as e:
            # here we don't use ignore_not_found, because elb raises:
            # BadRequest("Bad Request {'message': 'this healthcheck is
            # not exist', 'code': 'ELB.7020'}",)
            if 'ELB.7020' in e.message:
                return
            raise


def resource_mapping():
    return {
        'OSE::ELB::HealthCheck': HealthCheck,
    }
