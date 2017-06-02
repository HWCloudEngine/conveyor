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

from conveyor.api.wsgi import wsgi

from conveyor.api import extensions
from conveyor.resource import api as resource_api

from conveyor.i18n import _

LOG = logging.getLogger(__name__)


class ResourceActionController(wsgi.Controller):

    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(ResourceActionController, self).__init__(*args, **kwargs)
        self._resource_api = resource_api.ResourceAPI()
        self.ext_mgr = ext_mgr

    @wsgi.response(202)
    @wsgi.action("get_resource_detail")
    def _get_resource_detail(self, req, id, body):
        LOG.debug("Get resource detail.")

        if not self.is_valid_body(body, 'get_resource_detail'):
            msg = _("Get resource detail request body has not key 'get_resource_detail' \
                        or the format is incorrect")
            raise exc.HTTPBadRequest(explanation=msg)

        params = body['get_resource_detail']

        resource_type = params.get('type', None)

        if not resource_type:
            msg = _("The body should contain parameter 'type'.")
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            context = req.environ['conveyor.context']
            resource = self._resource_api.get_resource_detail(context,
                                                              resource_type,
                                                              id)
            return {"resource": resource}
        except Exception as e:
            LOG.error(unicode(e))
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
        res_azs = self.resource_api.list_plan_resource_availability_zones(
            context, plan_id)
        return {'availability_zones': res_azs}


class Resource(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Resource"
    alias = "conveyor-resource"
    namespace = "http://docs.openstack.org/conveyor/ext/resource/api/v1"
    updated = "2016-01-29T00:00:00+00:00"

    # extend exist resource
    def get_controller_extensions(self):
        controller = ResourceActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self,
                                                   'resources',
                                                   controller)
        return [extension]
