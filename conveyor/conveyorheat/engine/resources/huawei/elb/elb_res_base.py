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
import json

from oslo_log import log as logging
from oslo_serialization import jsonutils

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.engine import resource
from conveyor.conveyorheat.engine.resources.huawei.elb import utils
from conveyor.conveyorheat.engine import support

LOG = logging.getLogger(__name__)


class ElbBaseResource(resource.Resource):
    support_status = support.SupportStatus(version='2014.2')
    default_client_name = 'elb'

    def _prepare_properties(self, props):
        return dict((k, v) for k, v in props.items() if v is not None)

    def _set_job(self, data):
        self.data_set('job', jsonutils.dumps(data))

    def _get_job(self):
        data = self.data().get('job')
        return jsonutils.loads(data) if data else {}

    def _get_job_info(self, job_id):
        job = self.client('job').job.get(job_id)
        status = job.get('status')
        entities = job.get('entities')
        error_code = job.get('error_code')
        LOG.info(_('Job %(job)s details: status: %(status)s,  '
                   'error_code: %(e_code)s, '
                   'entities: %(entities)s')
                 % dict(job=job_id,
                        status=status,
                        e_code=error_code,
                        entities=entities))
        return status, entities, error_code

    def _check_job_success(self, job_id, ignore_not_found=False):
        job_status, entities, error_code = self._get_job_info(job_id)
        if job_status == utils.FAIL:
            # for the user case of delete
            if ignore_not_found:
                # the user case of delete loadbalancer or member if they
                # do not exist
                if error_code == 'NOT_FOUND_ERROR':
                    return True
                # the user case of remove members when listener has been
                # deleted, elb will raise ELB.2050: member listener not
                # belong to any loadbalancer
                error_msg = json.dumps(entities)
                if 'ELB.2050' in error_msg:
                    return True
            raise exception.ResourceUnknownStatus(
                result=(_('Job %(job)s failed: %(error_code)s, '
                          '%(entities)s')
                        % {'job': job_id,
                           'error_code': error_code,
                           'entities': entities}),
                resource_status='unknown')

        return job_status == utils.SUCCESS

    def _check_active(self, elb_status):
        if elb_status == utils.ACTIVE:
            return True
        if elb_status == utils.ERROR:
            raise exception.ResourceInError(
                resource_status=elb_status)
