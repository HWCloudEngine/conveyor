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
from oslo_utils import strutils
from oslo_utils import uuidutils

from conveyor.api import extensions
from conveyor.api.wsgi import wsgi
from conveyor.clone import api
from conveyor.common import plan_status as p_status
from conveyor.db import api as db_api
from conveyor import exception as conveyor_exception
from conveyor.plan import api as plan_api

from conveyor.i18n import _

LOG = logging.getLogger(__name__)


class PlansActionController(wsgi.Controller):

    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(PlansActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self.plan_api = plan_api.PlanAPI()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action('download_template')
    def _download_template(self, req, id, body):
        LOG.debug("download template of plan %s start in API from template",
                  id)
        context = req.environ['conveyor.context']
        plan = db_api.plan_get(context, id)
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
            LOG.error("Reset plan state request body has not key:\
                       os-reset_state")
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        update = body.get('os-reset_state')
        self.plan_api.update_plan(context, id, update)
        LOG.debug("End reset plan state in API for plan: %s", id)
        return {'plan_id': id, 'plan_status': update.get('plan_status')}

    @wsgi.response(202)
    @wsgi.action('force_delete-plan')
    def _force_delete_plan(self, req, id, body):

        if not self.is_valid_body(body, 'force_delete-plan'):
            LOG.error('Force delete plan request body has not key:'
                      'force_delete-plan')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('force_delete-plan', {}).get('plan_id', None)
        self.plan_api.force_delete_plan(context, plan_id)

    @wsgi.response(202)
    @wsgi.action('plan-delete-resource')
    def _plan_delete_resource(self, req, id, body):

        if not self.is_valid_body(body, 'plan-delete-resource'):
            LOG.error('Delete plan resource request body has not key:'
                      'plan-delete-resource')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('plan-delete-resource', {}).get('plan_id', None)
        self.plan_api.plan_delete_resource(context, plan_id)

    @wsgi.response(202)
    @wsgi.action("get_resource_detail_from_plan")
    def _get_resource_detail_from_plan(self, req, id, body):
        LOG.debug("Get resource detail from a plan")

        if not self.is_valid_body(body, 'get_resource_detail_from_plan'):
            msg = _("Request body hasn't key 'get_resource_detail_from_plan' \
                                    or the format is incorrect")
            raise exc.HTTPBadRequest(explanation=msg)

        params = body['get_resource_detail_from_plan']

        plan_id = params.get('plan_id')

        if not plan_id:
            msg = _("The body should contain parameter plan_id.")
            raise exc.HTTPBadRequest(explanation=msg)

        if not uuidutils.is_uuid_like(plan_id):
            msg = _("Invalid plan_id provided, plan_id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)

        is_original = params.get('is_original')
        if is_original:
            try:
                if strutils.bool_from_string(is_original, True):
                    is_original = True
                else:
                    is_original = False
            except ValueError as e:
                raise exc.HTTPBadRequest(explanation=unicode(e))
        else:
            is_original = False

        try:
            context = req.environ['conveyor.context']
            resource = \
                self.plan_api.get_resource_detail_from_plan(
                    context,
                    plan_id,
                    id,
                    is_original=is_original)
            return {"resource": resource}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action('plan_show-brief')
    def _plan_show_brief(self, req, id, body):

        if not self.is_valid_body(body, 'plan_show-brief'):
            LOG.error('Show plan brief body has not key:'
                      'plan-show-brief')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('plan_show-brief', {}).get('plan_id', None)
        try:
            plan = db_api.plan_get(context, plan_id)
            return {"plan": plan}
        except conveyor_exception.PlanNotFoundInDb:
            msg = 'Plan of %s not found' % plan_id
            raise exc.HTTPNotFound(explanation=msg)
        except Exception as e:
            LOG.error()
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action('list_plan_resource_availability_zones')
    def _list_plan_resource_availability_zones(self, req, id, body):
        if not self.is_valid_body(body,
                                  'list_plan_resource_availability_zones'):
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('list_plan_resource_availability_zones',
                           {}).get('plan_id', None)
        res_azs = self.plan_api.list_plan_resource_availability_zones(
            context, plan_id)
        return {'resource_availability_zones': res_azs}


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
