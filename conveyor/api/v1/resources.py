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

from conveyor.api import common
from conveyor.api.views import resources as views_resources
from conveyor.api.wsgi import wsgi

from conveyor.i18n import _
from conveyor.resource import api as resource_api

LOG = logging.getLogger(__name__)


class Controller(wsgi.Controller):
    """The resource API controller for the conveyor API."""

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self._viewBulid = views_resources.ViewBuilder()
        self._resource_api = resource_api.ResourceAPI()
        super(Controller, self).__init__()

    def show(self, req, id):
        return exc.HTTPNotImplemented()

    def delete(self, req, id):
        return exc.HTTPNotImplemented()

    def types(self, req):
        LOG.debug("Get the type of resources which can be cloned or migrated")
        context = req.environ['conveyor.context']
        type_list = self._resource_api.get_resource_types(context)
        return self._viewBulid.types(type_list)

    def detail(self, req):
        LOG.debug("Get resources of %s", req.GET.get('type', None))

        context = req.environ['conveyor.context']
        search_opts = {}
        search_opts.update(req.GET)

        resource_type = search_opts.get('type', None)
        if not resource_type:
            msg = _("SearchOptions don't contain argument 'type'.")
            LOG.error(msg)
            raise exc.HTTPBadRequest(explanation=msg)

        limit, marker = common.get_limit_and_marker(req)
        search_opts.pop("limit", None)
        search_opts.pop("marker", None)

        try:
            resources = self._resource_api.get_resources(
                            context,
                            search_opts=search_opts,
                            marker=marker, limit=limit)
            return {"resources": resources}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


def create_resource(ext_mgr):
    return wsgi.Resource(Controller(ext_mgr))
