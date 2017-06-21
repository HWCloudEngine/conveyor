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
from conveyor.plan import api as plan_api

LOG = logging.getLogger(__name__)


class MigrateActionController(wsgi.Controller):

    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(MigrateActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self._plan_api = plan_api.PlanAPI()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action('export_migrate_template')
    def _export_migrate_template(self, req, id, body):
        LOG.debug(" start exporting migrate template in API")
        context = req.environ['conveyor.context']
        self.clone_api.export_migrate_template(context, id)

    def _check_plan_resource_availability_zone(self, context,
                                               plan, destination):
        src_res_azs = self._plan_api.list_plan_resource_availability_zones(
            context, plan)
        for src_res_az in src_res_azs:
            if src_res_az not in destination:
                return False
        return True

    @wsgi.response(202)
    @wsgi.action('migrate')
    def _migrate(self, req, id, body):
        LOG.error('liuling begin time of migrate is %s'
                  % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        LOG.debug(" start execute migrate plan in API,the plan id is %s" % id)
        context = req.environ['conveyor.context']
        if not self.is_valid_body(body, 'migrate'):
            LOG.debug("migrate request body has not key:migrate")
            raise exc.HTTPUnprocessableEntity()
        migrate_body = body['migrate']
        destination = migrate_body.get('destination')
        if not isinstance(destination, dict):
            msg = _("The parameter 'destination' must be a map.")
            raise exc.HTTPBadRequest(explanation=msg)
        if not self._check_plan_resource_availability_zone(context,
                                                           id,
                                                           destination):
            msg = _("The destination %(destination)s does not contain all "
                    "resource availability_zone of plan %{plan_id)s") % {
                      'destination': destination,
                      'plan_id': id
                  }
            raise exc.HTTPBadRequest(explanation=msg)
        self.clone_api.migrate(context, id, destination)


class Migrate(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Migrate"
    alias = "conveyor-Migrate"
    namespace = "http://docs.openstack.org/conveyor/ext/migrate/api/v1"
    updated = "2016-01-29T00:00:00+00:00"

    # extend exist resource
    def get_controller_extensions(self):
        controller = MigrateActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'migrates',
                                                   controller)
        return [extension]
