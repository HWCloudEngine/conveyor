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
#
#    Copyright 2015 IBM Corp.

from neutronclient.common import exceptions as qe

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine.clients.os import nova
from conveyor.conveyorheat.engine import constraints
from conveyor.i18n import _

CLIENT_NAME = 'neutron'


class NetworkConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (qe.NeutronClientException,
                           exception.EntityNotFound,
                           exception.PhysicalResourceNameAmbiguity)

    def validate_with_client(self, client, value):
        try:
            client.client(CLIENT_NAME)
        except Exception:
            # is not using neutron
            client.client_plugin(nova.CLIENT_NAME).get_nova_network_id(value)
        else:
            neutron_plugin = client.client_plugin(CLIENT_NAME)
            neutron_plugin.find_resourceid_by_name_or_id(
                'network', value, cmd_resource=None)


class NeutronConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (qe.NeutronClientException,
                           exception.EntityNotFound)
    resource_name = None
    cmd_resource = None
    extension = None

    def validate_with_client(self, client, value):
        neutron_plugin = client.client_plugin(CLIENT_NAME)
        if (self.extension and
                not neutron_plugin.has_extension(self.extension)):
            raise exception.EntityNotFound(entity='neutron extension',
                                           name=self.extension)
        neutron_plugin.find_resourceid_by_name_or_id(
            self.resource_name, value, cmd_resource=self.cmd_resource)


class PortConstraint(NeutronConstraint):
    resource_name = 'port'


class RouterConstraint(NeutronConstraint):
    resource_name = 'router'


class SubnetConstraint(NeutronConstraint):
    resource_name = 'subnet'


class SubnetPoolConstraint(NeutronConstraint):
    resource_name = 'subnetpool'


class AddressScopeConstraint(NeutronConstraint):
    resource_name = 'address_scope'
    extension = 'address-scope'


class QoSPolicyConstraint(NeutronConstraint):
    resource_name = 'policy'
    cmd_resource = 'qos_policy'
    extension = 'qos'


class ProviderConstraint(constraints.BaseCustomConstraint):

    expected_exceptions = (exception.StackValidationFailed,)
    service_type = None

    def validate_with_client(self, client, value):
        params = {}
        neutron_client = client.client(CLIENT_NAME)
        if self.service_type:
            params['service_type'] = self.service_type
        providers = neutron_client.list_service_providers(
            retrieve_all=True,
            **params
        )['service_providers']
        names = [provider['name'] for provider in providers]
        if value not in names:
            not_found_message = (
                _("Unable to find neutron provider '%(provider)s', "
                  "available providers are %(providers)s.") %
                {'provider': value, 'providers': names}
            )
            raise exception.StackValidationFailed(message=not_found_message)


class LBaasV1ProviderConstraint(ProviderConstraint):
    service_type = 'LOADBALANCER'
