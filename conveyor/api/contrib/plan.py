# Copyright 2011 OpenStack Foundation
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
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


from webob import exc

from oslo_log import log as logging

from conveyor.api import extensions
from conveyor.api.wsgi import wsgi
from conveyor.clone import api
from conveyor.common import plan_status as p_status
from conveyor.resource import api as resource_api

from conveyor.i18n import _

LOG = logging.getLogger(__name__)


class PlansActionController(wsgi.Controller):

    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(PlansActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self.resource_api = resource_api.ResourceAPI()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action('download_template')
    def _download_template(self, req, id, body):
        LOG.debug("download template of plan %s start in API from template",
                  id)
        context = req.environ['conveyor.context']
        plan = self.resource_api.get_plan_by_id(context, id)
        plan_status = plan['plan_status']
        if plan_status not in (p_status.AVAILABLE, p_status.CLONING,
                               p_status.MIGRATING, p_status.FINISHED):
            msg = _("the plan %(plan_id)s in state %(state)s"
                    "can't download template") % {
                    'plan_id': id,
                    'state': plan_status,
                }
            raise exc.HTTPBadRequest(explanation=msg)
        content = self.clone_api.download_template(context, id)
        LOG.debug('the content is %s' % content)
        return content

    @wsgi.response(202)
    @wsgi.action('os-reset_state')
    def _reset_state(self, req, id, body):

        LOG.debug("Start reset plan state in API for plan: %s", id)
        if not self.is_valid_body(body, 'os-reset_state'):
            LOG.debug("Reset plan state request body has not key:\
                       os-reset_state")
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        update = body.get('os-reset_state')
        self.resource_api.update_plan(context, id, update)
        LOG.debug("End reset plan state in API for plan: %s", id)
        return {'plan_id': id, 'plan_status': update.get('plan_status')}

    @wsgi.response(202)
    @wsgi.action('force_delete-plan')
    def _force_delete_plan(self, req, id, body):

        if not self.is_valid_body(body, 'force_delete-plan'):
            LOG.debug('')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('force_delete-plan', {}).get('plan_id', None)
        self.resource_api.force_delete_plan(context, plan_id)

    @wsgi.response(202)
    @wsgi.action('plan-delete-resource')
    def _plan_delete_resource(self, req, id, body):

        if not self.is_valid_body(body, 'plan-delete-resource'):
            LOG.debug('')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('plan-delete-resource', {}).get('plan_id', None)
        self.resource_api.plan_delete_resource(context, plan_id)


class Plan(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Plan"
    alias = "conveyor-plan"
    namespace = "http://docs.openstack.org/conveyor/ext/plan/api/v1"
    updated = "2016-01-29T00:00:00+00:00"

    # extend exist resource
    def get_controller_extensions(self):
        controller = PlansActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'plans', controller)
        return [extension]
