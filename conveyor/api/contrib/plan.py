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

  
class PlansActionController(wsgi.Controller):
    
    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(PlansActionController, self).__init__(*args, **kwargs)
        self.clone_api = api.API()
        self.ext_mgr = ext_mgr
    
    @wsgi.response(202)
    @wsgi.action('download_template')
    def _download_template(self, req, id, body):
        
        LOG.debug("download_template start in API from template")
  
        context = req.environ['conveyor.context']
        content = self.clone_api.download_template(context, id)
        LOG.debug('the content is %s' %content)
        return content
  
class Plan(extensions.ExtensionDescriptor):
    """Enable admin actions."""

    name = "Plan"
    alias = "conveyor-plan"
    namespace = "http://docs.openstack.org/conveyor/ext/plan/api/v1"
    updated = "2016-01-29T00:00:00+00:00"
    
    
    #extend exist resource
    def get_controller_extensions(self):
        controller = PlansActionController(self.ext_mgr)
        extension = extensions.ControllerExtension(self, 'plans', controller)
        return [extension]    
