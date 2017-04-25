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

from oslo_log import log as logging
from oslo_serialization import jsonutils as json
import webob

from conveyor.conveyorheat.common import wsgi

LOG = logging.getLogger(__name__)


class IAMProjectID(wsgi.Middleware):
    """Set project_id in request context"""

    def __init__(self, app, conf):
        self.conf = conf
        self.application = app

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        if req.context.tenant_id:
            LOG.info("found tenant_id in context, continue")
            return self.application

        if req.body:
            body = json.loads(req.body)
            metadata = body.get('meta_data')
            req.context.tenant_id =\
                metadata.get('project_id') if metadata else None

        return self.application


def IAMProjectID_filter_factory(global_conf, **local_conf):
    """Factory method for paste.deploy"""

    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return IAMProjectID(app, conf)

    return filter
