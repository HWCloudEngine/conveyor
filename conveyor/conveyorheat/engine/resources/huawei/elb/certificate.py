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

from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.elb import elb_res_base


class Certificate(elb_res_base.ElbBaseResource):
    """A resource for certificate .

    Certificate resource for Elastic Load Balance Service.
    """

    PROPERTIES = (
        NAME, DESCRIPTION, CERTIFICATE, PRIVATE_KEY,
    ) = (
        'name', 'description', 'certificate', 'private_key',
    )

    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('The name of certificate.'),
            update_allowed=True
        ),
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('The description of the certificate.'),
            update_allowed=True
        ),
        CERTIFICATE: properties.Schema(
            properties.Schema.STRING,
            _('PEM-formatted certificate chain.'),
            required=True
        ),
        PRIVATE_KEY: properties.Schema(
            properties.Schema.STRING,
            _('PEM-formatted private_key chain.'),
            required=True
        ),
    }

    def handle_create(self):
        props = self._prepare_properties(self.properties)
        cert = self.client().certificate.create(**props)
        self.resource_id_set(cert.id)

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            self.client().certificate.update(certificate_id=self.resource_id,
                                             **prop_diff)

    def handle_delete(self):
        return
        # if not self.resource_id:
        #     return
        # try:
        #     self.client().certificate.delete(self.resource_id)
        # except Exception as e:
        #     # here we don't use ignore_not_found, because elb raises:
        #     # BadRequest("Bad Request {'message': 'The certificate is
        #     # not exist', 'code': 'ELB.5005'}",)
        #     if 'ELB.5005' in e.message:
        #         return
        #     raise


def resource_mapping():
    return {
        'OSE::ELB::Certificate': Certificate,
    }
