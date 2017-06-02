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

LOG = logging.getLogger(__name__)


class CloneActionController(wsgi.Controller):
    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(CloneActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action('clone_element_template')
    def _start_template_clone(self, req, id, body):
        LOG.debug("Clone start in API from template")
        if not self.is_valid_body(body, 'clone_element_template'):
            LOG.debug("Clone template request body has not key:\
                       clone_element_template")
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        temp_info = body['clone_element_template']
        template = temp_info['template']
        # remove plan type info
        if 'plan_type' in template:
            template.pop('plan_type')
        LOG.debug("Clone from template: %s", temp_info)
        self.clone_api.start_template_clone(context, temp_info)

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

    def _check_plan_resource_availability_zone(self, context,
                                               plan, destination):
        src_res_azs = self._resource_api.list_plan_resource_availability_zones(
            context, plan)
        for src_res_az in src_res_azs:
            if src_res_az not in destination:
                return False
        return True

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
        if plan_status not in (p_status.AVAILABLE, p_status.CLONING,
                               p_status.MIGRATING,
                               p_status.FINISHED,):
            msg = _("the plan %(plan_id)s in state %(state)s can't clone") % {
                'plan_id': id,
                'state': plan_status,
            }
            raise exc.HTTPBadRequest(explanation=msg)
        clone_body = body['clone']
        destination = clone_body.get('destination')
        if not isinstance(destination, dict):
            msg = _("The parameter 'destination' must be a map.")
            if not self._check_plan_resource_availability_zone(context,
                                                               plan,
                                                               destination):
                msg = _("The destination %(destination)s does not contain all "
                        "resource availability_zone of plan %{plan_id)s") % {
                          'destination': destination,
                          'plan_id': id
                      }
                raise exc.HTTPBadRequest(explanation=msg)
            raise exc.HTTPBadRequest(explanation=msg)
        sys_clone = clone_body.get('sys_clone', False)
        # copy_data = clone_body.get('copy_data', True)
        context = req.environ['conveyor.context']
        self.clone_api.clone(context, id, destination, sys_clone)

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

        if not self._check_plan_resource_availability_zone(context,
                                                           plan,
                                                           destination):
            msg = _("The destination %(destination)s does not contain all "
                    "resource availability_zone of plan %{plan_id)s") % {
                'destination': destination,
                'plan_id': id
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
