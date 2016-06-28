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

from conveyor import context
from conveyor.common import log as logging
from conveyor.api.wsgi import wsgi
from conveyor.api import extensions

from conveyor.common import timeutils
from conveyor.clone import api

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
            LOG.debug("Clone template request body has not key:clone_element_template")
            raise exc.HTTPUnprocessableEntity()    
        
        context = req.environ['conveyor.context']
            
        temp_info = body['clone_element_template']
        template = temp_info['template']
        expire_time = template['expire_time']
        expire_time = timeutils.parse_isotime(expire_time)
        
        # check template is outtime or not
        if timeutils.is_older_than(expire_time, 0):
            msg = _("Template is out of time")
            raise exc.HTTPBadRequest(explanation=msg)
            
        #call clone manager api
        #remove expire_time info in template
        template.pop('expire_time')
        #remove plan type info
        if template.has_key('plan_type'):
            template.pop('plan_type')
        
        LOG.debug("Clone from template: %s", temp_info)
        self.clone_api.start_template_clone(context, temp_info)
        
    
    @wsgi.response(202)
    @wsgi.action('export_clone_template')
    def _export_clone_template(self, req, id, body):  
        LOG.debug(" start exporting template in API")
        if not self.is_valid_body(body, 'export_clone_template'):
            LOG.debug("export template request body has not key:export_clone_template")
            raise exc.HTTPUnprocessableEntity() 
          
        export_Template = body['export_clone_template']
        clone_element = export_Template.get('update_resources')
        context = req.environ['conveyor.context']
        self.clone_api.export_clone_template(context, id, clone_element)
        
        
    @wsgi.response(202)
    @wsgi.action('clone')
    def _clone(self, req, id, body):  
        LOG.debug(" start execute clone plan in API,the plan id is %s" %id)
        if not self.is_valid_body(body, 'clone'):
            LOG.debug("clone request body has not key:clone")
            raise exc.HTTPUnprocessableEntity() 
          
        clone_body = body['clone']
        destination = clone_body.get('destination')
        update_resources = clone_body.get('update_resources')
        context = req.environ['conveyor.context']
        self.clone_api.clone(context, id, destination, update_resources)
        
        


class Clone(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Clone"
    alias = "conveyor-Clone"
    namespace = "http://docs.openstack.org/conveyor/ext/clone/api/v1"
    updated = "2016-01-29T00:00:00+00:00"
    
    
    #extend exist resource
    def get_controller_extensions(self):
        controller = CloneActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'clones', controller)
        return [extension]    
