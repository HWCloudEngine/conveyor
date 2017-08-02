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


import six
from webob import exc

from oslo_log import log as logging
from oslo_utils import uuidutils

from conveyor.api import common
from conveyor.api.wsgi import wsgi
from conveyor.common import plan_status as p_status
from conveyor.common import template_format
from conveyor.db import api as db_api
from conveyor.i18n import _
from conveyor.plan import api as plan_api

LOG = logging.getLogger(__name__)


class Controller(wsgi.Controller):
    """The plan API controller for the conveyor API."""

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self._plan_api = plan_api.PlanAPI()
        super(Controller, self).__init__()

    def show(self, req, id):
        LOG.debug("Get plan with id of %s.", id)

        if not uuidutils.is_uuid_like(id):
            msg = _("Invalid id provided, id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']

        try:
            plan = db_api.plan_get(context, id)
            return {"plan": plan}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    def create(self, req, body):
        LOG.debug("Create a clone or migrate plan.")

        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']
        params = body["plan"]

        resources = []

        if not params.get('plan_type'):
            msg = _('The body should contain type information.')
            raise exc.HTTPBadRequest(explanation=msg)

        for res in params.get('clone_obj', []):
            if not isinstance(res, dict):
                msg = _("Every resource must be a dict with id and type keys.")
                raise exc.HTTPBadRequest(explanation=msg)

            res_id = res.get('obj_id')
            res_type = res.get('obj_type')
            if not res_id or not res_type:
                msg = _('Type or id is empty')
                raise exc.HTTPBadRequest(explanation=msg)
            if res_type not in p_status.RESOURCE_TYPES:
                msg = _('Type does not support')
                raise exc.HTTPBadRequest(explanation=msg)
            resources.append({'obj_id': res_id, 'obj_type': res_type})

        if not resources:
            msg = _('No vaild resource, please check the types and ids')
            raise exc.HTTPBadRequest(explanation=msg)

        plan_name = params.get('plan_name')

        try:
            plan_dict = \
                self._plan_api.create_plan(context, params.get('plan_type'),
                                           resources,
                                           plan_name=plan_name)
            plan_dict['clone_obj'] = plan_dict['clone_resources']
            plan_dict.pop('clone_resources', None)
            return {'plan': plan_dict}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    def create_plan_by_template(self, req, body):

        LOG.debug("Create a plan by template")

        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']

        tpl_param = body['plan'].get('template')
        if not tpl_param:
            msg = _('No template found in body.')
            raise exc.HTTPBadRequest(explanation=msg)

        template = self._convert_template_to_json(tpl_param)

        plan_type = template.get('plan_type')

        if not plan_type:
            msg = _("Template must have 'plan_type' field.")
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            plan_name = body['plan'].get('plan_name', None)
            plan = self._plan_api.create_plan_by_template(context,
                                                          template,
                                                          plan_name=plan_name)
            return {"plan": plan}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    def _convert_template_to_json(self, template):
        if isinstance(template, dict):
            return template
        elif isinstance(template, six.string_types):
            LOG.debug("Convert template from string to map")
            return template_format.parse(template)
        else:
            msg = _("Template must be string or map.")
            raise exc.HTTPBadRequest(explanation=msg)

    def delete(self, req, id):
        LOG.debug("Delete plan <%s>.", id)

        if not uuidutils.is_uuid_like(id):
            msg = _("Invalid id provided, id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']

        try:
            self._plan_api.delete_plan(context, id)
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action('update_plan_resources')
    def _update_plan_resources(self, req, id, body):
        """Update resource of specific plan."""

        if not self.is_valid_body(body, 'update_plan_resources'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']
        update_values = body['update_plan_resources'].get('resources')

        if not update_values:
            msg = _('No resources found in body.')
            raise exc.HTTPBadRequest(explanation=msg)

        LOG.debug("Update resource of plan <%s> with values: %s",
                  id, update_values)

        try:
            self._plan_api.update_plan_resources(context,
                                                 id,
                                                 update_values)
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    def update(self, req, id, body):
        """Update a plan."""
        LOG.debug("Update a plan.")

        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']
        update_values = body['plan']

        try:
            self._plan_api.update_plan(context, id, update_values)
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    def detail(self, req):
        LOG.debug("Get all plans.")
        search_opts = {}
        search_opts.update(req.GET)
        context = req.environ['conveyor.context']

        limit, marker = common.get_limit_and_marker(req)
        search_opts.pop('limit', None)
        search_opts.pop('marker', None)
        sort_keys, sort_dirs = common.get_sort_params(search_opts)

        all_tenants = common.is_all_tenants(search_opts)
        search_opts.pop('all_tenants', None)
        if not all_tenants:
            if context.project_id:
                search_opts['project_id'] = context.project_id
            else:
                search_opts['user_id'] = context.user_id

        filters = search_opts.copy()
        LOG.info("limit=%s, marker=%s, sort_keys=%s, sort_dirs=%s filter=%s",
                 limit, marker, sort_keys, sort_dirs, filters)
        plans = self._plan_api.get_plans(context, marker=marker,
                                         limit=limit,
                                         sort_dirs=sort_dirs,
                                         sort_keys=sort_keys,
                                         filters=filters)

        return {"plans": plans}


def create_resource(ext_mgr):
    return wsgi.Resource(Controller(ext_mgr))
