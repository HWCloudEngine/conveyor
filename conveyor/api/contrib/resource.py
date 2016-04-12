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

from conveyor.i18n import _
from conveyor import context
from conveyor.common import log as logging
from conveyor.common import uuidutils
from conveyor.api.wsgi import wsgi
from conveyor.api import extensions

from conveyor.resource import api as resource_api

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
        
        context = req.environ['conveyor.context']
        params = body['get_resource_detail']
        
        resource_type = params.get('type', None)
        
        if not resource_type:
            msg = _("The body should contain parameter 'type'.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        try:
            resource = self._resource_api.get_resource_detail(context, 
                                                              resource_type, id)
            return {"resource": resource}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


    @wsgi.response(202)
    @wsgi.action("get_resource_detail_from_plan")
    def _get_resource_detail_from_plan(self, req, id, body):
        LOG.debug("Get resource detail from a plan")
        
        if not self.is_valid_body(body, 'get_resource_detail_from_plan'):
            msg = _("Request body hasn't key 'get_resource_detail_from_plan' \
                                    or the format is incorrect")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        params = body['get_resource_detail_from_plan']
        
        plan_id = params.get('plan_id', None)
        
        if not plan_id:
            msg = _("The body should contain parameter plan_id.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        if not uuidutils.is_uuid_like(plan_id):
            msg = _("Invalid plan_id provided, plan_id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        try:
            resource = self._resource_api.get_resource_detail_from_plan(context, 
                                                                        plan_id, id)
            return {"resource": resource}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


class Resource(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Resource"
    alias = "conveyor-resource"
    namespace = "http://docs.openstack.org/conveyor/ext/resource/api/v1"
    updated = "2016-01-29T00:00:00+00:00"
    
    #extend exist resource
    def get_controller_extensions(self):
        controller = ResourceActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'resources', controller)
        return [extension]    
