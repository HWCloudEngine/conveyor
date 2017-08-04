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
            msg = _("Get resource detail request body has not key  \
                        'get_resource_detail'or the format is incorrect")
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
    @wsgi.action("list-clone_resources_attribute")
    def list_clone_resources_attribute(self, req, id, body):
        if not self.is_valid_body(body, 'list-clone_resources_attribute'):
            msg = _("Get resource detail request body has not key  \
                        'list-clone_resources_attribute'")
            raise exc.HTTPBadRequest(explanation=msg)
        params = body['list-clone_resources_attribute']
        plan_id = params.get('plan_id', None)
        attribute = params.get('attribute_name', None)
        try:
            context = req.environ['conveyor.context']
            attribute_list = \
                self._resource_api.list_clone_resources_attribute(context,
                                                                  plan_id,
                                                                  attribute)
            return {'attribute_list': attribute_list}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action("list-all_availability_zones")
    def list_all_availability_zones(self, req, id, body):
        try:
            context = req.environ['conveyor.context']
            search_opts = {}
            search_opts['type'] = 'OS::Nova::AvailabilityZone'
            az_list = \
                self._resource_api.get_resources(context, search_opts)
            return {'availability_zone_list': az_list}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action("build-resources_topo")
    def build_resources_topo(self, req, id, body):
        if not self.is_valid_body(body, 'build-resources_topo'):
            msg = _("Get resource detail request body has not key  \
                        'list-clone_resources_attribute'")
            raise exc.HTTPBadRequest(explanation=msg)
        params = body['build-resources_topo']
        plan_id = params.get('plan_id', '')
        az_map = params.get('availability_zone_map', {})
        search_opt = params.get('search_opt', None)
        try:
            context = req.environ['conveyor.context']
            topo = self._resource_api.build_resources_topo(
                context, plan_id, az_map, search_opt=search_opt)
            return {'plan_id': plan_id, 'topo': topo}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))

    @wsgi.response(202)
    @wsgi.action('delete-cloned_resource')
    def _delete_cloned_resource(self, req, id, body):

        if not self.is_valid_body(body, 'delete-cloned_resource'):
            LOG.error('Delete plan resource request body has not key:'
                      'plan-delete-resource')
            raise exc.HTTPUnprocessableEntity()
        context = req.environ['conveyor.context']
        plan_id = body.get('delete-cloned_resource', {}).get('plan_id', None)
        self._resource_api.delete_cloned_resource(context, plan_id)


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
