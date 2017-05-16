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

from oslo_log import log as logging

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.engine import attributes
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.elb import elb_res_base
from conveyor.conveyorheat.engine.resources.huawei.elb import utils

LOG = logging.getLogger(__name__)


class LoadBalancer(elb_res_base.ElbBaseResource):
    """A resource for ELB Loadbalancer.

    Load Balancer resource for Elastic Load Balance Service.
    """

    PROPERTIES = (
        NAME, DESCRIPTION, VPC_ID, BANDWIDTH, TYPE,
        ADMIN_STATE_UP, VIP_SUBNET, AVAILABILITY_ZONE, SECURITY_GROUP,
    ) = (
        'name', 'description', 'vpc_id', 'bandwidth', 'type',
        'admin_state_up', 'vip_subnet_id', 'az', 'security_group',
    )

    _LB_TYPES = (
        EXTERNAL, INTERNAL,
    ) = (
        'External', 'Internal',
    )

    ATTRIBUTES = (
        VIP_ADDRESS_ATTR, VIP_SUBNET_ATTR, STATUS_ATTR,
    ) = (
        'vip_address', VIP_SUBNET, 'status',
    )
    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('The name of the load balancer.'),
            required=True,
            update_allowed=True,
            constraints=[
                constraints.AllowedPattern('^[0-9a-zA-Z-_]{1,64}$')]
        ),
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('The description of the load balancer.'),
            update_allowed=True,
            constraints=[constraints.AllowedPattern('^[^<>]{1,128}$')]
        ),
        VPC_ID: properties.Schema(
            properties.Schema.STRING,
            _('The ID of vpc.'),
            required=True,
            constraints=[
                constraints.CustomConstraint('neutron.router')
            ]
        ),
        BANDWIDTH: properties.Schema(
            properties.Schema.INTEGER,
            _('The bandwidth of the load balancer, in Mbit/s.'),
            constraints=[
                constraints.Range(min=1, max=300)
            ],
            update_allowed=True
        ),
        TYPE: properties.Schema(
            properties.Schema.STRING,
            _('The type of the load balancer.'),
            constraints=[
                constraints.AllowedValues(_LB_TYPES)
            ],
            required=True
        ),
        ADMIN_STATE_UP: properties.Schema(
            properties.Schema.BOOLEAN,
            _('The admin state of the load balancer.'),
            update_allowed=True,
            default=True
        ),
        VIP_SUBNET: properties.Schema(
            properties.Schema.STRING,
            _('The ID of the network on which to allocate the VIP.'),
            constraints=[
                constraints.CustomConstraint('neutron.network')
            ]
        ),
        AVAILABILITY_ZONE: properties.Schema(
            properties.Schema.STRING,
            _('The ID of the availability zone.'),
        ),
        SECURITY_GROUP: properties.Schema(
            properties.Schema.STRING,
            _('The ID of the security group.'),
        ),
    }

    attributes_schema = {
        VIP_ADDRESS_ATTR: attributes.Schema(
            _('The vip address of the load balancer.'),
        ),
        VIP_SUBNET_ATTR: attributes.Schema(
            _('The vip subnet of the load balancer.'),
        ),
        STATUS_ATTR: attributes.Schema(
            _('The status of the load balancer.'),
        ),
    }

    def validate(self):
        super(LoadBalancer, self).validate()
        lb_type = self.properties[self.TYPE]
        bandwidth = self.properties[self.BANDWIDTH]
        vip_subnet = self.properties[self.VIP_SUBNET]
        az = self.properties[self.AVAILABILITY_ZONE]
        sec_group = self.properties[self.SECURITY_GROUP]

        if lb_type == self.EXTERNAL:
            if not bandwidth:
                msg = (_('The %(bdw)s must be provided when lb is %(type)s.') %
                       {'bdw': self.BANDWIDTH,
                        'type': lb_type})
                raise exception.StackValidationFailed(message=msg)
        elif lb_type == self.INTERNAL:
            if vip_subnet is None or az is None or sec_group is None:
                msg = (_('The %(sub)s, %(az)s and %(sg)s must be provided '
                         'when lb is %(type)s.') %
                       {'sub': self.VIP_SUBNET,
                        'az': self.AVAILABILITY_ZONE,
                        'sg': self.SECURITY_GROUP,
                        'type': lb_type})
                raise exception.StackValidationFailed(message=msg)

    def _resolve_attribute(self, name):
        if not self.resource_id:
            return None

        elb = self.client().loadbalancer.get(self.resource_id)
        if name == self.VIP_ADDRESS_ATTR:
            return elb.vip_address
        if name == self.VIP_SUBNET_ATTR:
            return elb.vip_subnet_id
        if name == self.STATUS_ATTR:
            return elb.status

    def handle_create(self):
        props = self._prepare_properties(self.properties)
        job_id = self.client().loadbalancer.create(**props)['job_id']
        job_info = {'job_id': job_id, 'action': self.action}
        self._set_job(job_info)
        return job_id

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            return self.client().loadbalancer.update(
                loadbalancer_id=self.resource_id, **prop_diff)['job_id']

    def handle_delete(self):
        if not self.resource_id:
            job_info = self._get_job()
            job_id = job_info.get('job_id')
            if not job_id:
                return

            try:
                job_status, entities, error_code = self._get_job_info(job_id)
            except Exception as e:
                if self.client_plugin().is_not_found(e):
                    LOG.info('job %s not found', job_id)
                    return
                raise e

            elb_info = entities.get('elb', {})
            elb_id = elb_info.get('id')
            if not elb_id:
                return
            self.resource_id_set(elb_id)

        try:
            lb = self.client().loadbalancer.get(self.resource_id)
            return self.client().loadbalancer.delete(lb.id)['job_id']
        except Exception as e:
            self.client_plugin().ignore_not_found(e)

    def check_create_complete(self, job_id):
        if self.resource_id is None:
            job_status, entities, error_code = self._get_job_info(job_id)
            elb_status = 'unknown'
            if entities:
                elb_info = entities.get('elb', {})
                elb_id = elb_info.get('id')
                elb_status = elb_info.get('status')
                if elb_id:
                    self.resource_id_set(elb_id)
                    self._set_job({})
            if job_status == utils.FAIL:
                self._set_job({})
                raise exception.ResourceUnknownStatus(
                    result=(_('Job %(job)s failed: %(error_code)s, '
                              '%(entities)s')
                            % {'job': job_id,
                               'error_code': error_code,
                               'entities': entities}),
                    resource_status=elb_status)
            return self._check_active(elb_status)
        else:
            elb = self.client().loadbalancer.get(self.resource_id)
            return self._check_active(elb.status)

    def check_update_complete(self, job_id):
        if not job_id:
            return True
        return self._check_job_success(job_id)

    def check_delete_complete(self, job_id):
        if not job_id:
            return True
        return self._check_job_success(job_id, ignore_not_found=True)


def resource_mapping():
    return {
        'OSE::ELB::LoadBalancer': LoadBalancer,
    }
