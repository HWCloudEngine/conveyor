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

import time
from webob import exc

from oslo_log import log as logging

from conveyor.api import extensions
from conveyor.api.wsgi import wsgi
from conveyor.clone import api
from conveyor.common import plan_status as p_status
from conveyor.db import api as db_api
from conveyor.i18n import _
from conveyor.plan import api as plan_api

LOG = logging.getLogger(__name__)


class CloneActionController(wsgi.Controller):
    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(CloneActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self._plan_api = plan_api.PlanAPI()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action('export_clone_template')
    def _export_clone_template(self, req, id, body):
        LOG.debug(" start exporting template in API")
        context = req.environ['conveyor.context']
        plan = db_api.plan_get(context, id)
        plan_status = plan['plan_status']
        if plan_status not in (p_status.INITIATING, p_status.CREATING):
            msg = _('the plan %(plan_id)s in state %(state)s'
                    " can't export template") % {'plan_id': id,
                                                 'state': plan_status}
            raise exc.HTTPBadRequest(explanation=msg)
        clone_body = body['export_clone_template']
        sys_clone = clone_body.get('sys_clone', False)
        copy_data = clone_body.get('copy_data', True)
        self.clone_api.export_clone_template(context, id, sys_clone, copy_data)

    @wsgi.response(202)
    @wsgi.action('clone')
    def _clone(self, req, id, body):
        LOG.error('begin time of clone is %s'
                  % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        LOG.debug("start execute clone plan in API,the plan id is %s" % id)
        context = req.environ['conveyor.context']
        if not self.is_valid_body(body, 'clone'):
            LOG.debug("clone request body has not key:clone")
            raise exc.HTTPUnprocessableEntity()
        plan = db_api.plan_get(context, id)
        plan_status = plan['plan_status']
        if plan_status not in (p_status.AVAILABLE,
                               p_status.MIGRATING,
                               p_status.FINISHED,):
            msg = _("the plan %(plan_id)s in state %(state)s can't clone") % {
                'plan_id': id,
                'state': plan_status,
            }
            raise exc.HTTPBadRequest(explanation=msg)
        clone_body = body['clone']
        plan_id = clone_body.get('plan_id')
        az_map = clone_body.get('availability_zone_map')
        clone_resources = clone_body.get('clone_resources', [])
        clone_links = clone_body.get('clone_links', [])
        update_resources = clone_body.get('update_resources', [])
        replace_resources = clone_body.get('replace_resources', [])
        sys_clone = clone_body.get('sys_clone', False)
        data_copy = clone_body.get('copy_data', True)
        LOG.debug("Clone Resources: %(res)s, "
                  "the replaces: %(link)s, the update: %(up)s",
                  {'res': clone_resources,
                   'link': replace_resources, 'up': update_resources})
        if not isinstance(az_map, dict):
            msg = _("The parameter 'destination' must be a map.")
            raise exc.HTTPBadRequest(explanation=msg)
        context = req.environ['conveyor.context']
        self.clone_api.clone(context, plan_id, az_map, clone_resources,
                             clone_links, update_resources, replace_resources,
                             sys_clone, data_copy)

    @wsgi.response(202)
    @wsgi.action('export_template_and_clone')
    def _export_template_and_clone(self, req, id, body):
        LOG.debug("start export_template_and_clone,the plan id is %s" % id)
        context = req.environ['conveyor.context']
        if not self.is_valid_body(body, 'export_template_and_clone'):
            LOG.debug("clone request body has not key:clone")
            raise exc.HTTPUnprocessableEntity()
        clone_body = body['export_template_and_clone']
        destination = clone_body.get('destination')
        if not isinstance(destination, dict):
            msg = _("The parameter 'destination' must be a map.")
            raise exc.HTTPBadRequest(explanation=msg)
        sys_clone = clone_body.get('sys_clone', False)
        copy_data = clone_body.get('copy_data', True)
        resources = clone_body.get('resources')
        plan = db_api.plan_get(context, id)
        plan_status = plan['plan_status']
        if plan_status not in (p_status.INITIATING, p_status.AVAILABLE,
                               p_status.FINISHED, p_status.CREATING):
            msg = _("the plan %(plan_id)s in state %(state)s"
                    "can't export_template_and_clone") % {
                      'plan_id': id,
                      'state': plan_status,
                  }
            raise exc.HTTPBadRequest(explanation=msg)
        self.clone_api.export_template_and_clone(context, id, destination,
                                                 resources, sys_clone,
                                                 copy_data)


class Clone(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Clone"
    alias = "conveyor-Clone"
    namespace = "http://docs.openstack.org/conveyor/ext/clone/api/v1"
    updated = "2016-01-29T00:00:00+00:00"

    # extend exist resource
    def get_controller_extensions(self):
        controller = CloneActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'clones', controller)
        return [extension]
