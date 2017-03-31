# Copyright 2012, Intel, Inc.
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
from oslo_config import cfg
from oslo_log import log as logging

from conveyor.clone import rpcapi


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class API(object):

    def __init__(self):
        self.clone_rpcapi = rpcapi.CloneAPI()
        super(API, self).__init__()

    def start_template_clone(self, context, template):
        LOG.debug("Clone template start in Clone api mode")
        self.clone_rpcapi.start_template_clone(context, template)

    def export_clone_template(self, context, id, sys_clone):
        LOG.debug("export clone template of elements")
        self.clone_rpcapi.export_clone_template(context, id, sys_clone)

    def clone(self, context, id, destination, sys_clone):
        LOG.debug("execute clone plan in clone api")
        self.clone_rpcapi.clone(context, id, destination, sys_clone)

    def export_migrate_template(self, context, id):
        LOG.debug("export migrate template of plan %s" % id)
        self.clone_rpcapi.export_migrate_template(context, id)

    def migrate(self, context, id, destination): 
        LOG.debug("execute migrate plan %s in  api" % id)
        self.clone_rpcapi.migrate(context, id, destination)

    def download_template(self, context, id):
        LOG.debug("download template of plan %s" % id)
        return self.clone_rpcapi.download_template(context, id)

    def export_template_and_clone(self, context, id, destination,
                                  update_resources={},
                                  sys_clone=False):
        LOG.debug("export template and clone plan %s" % id)
        return self.clone_rpcapi.export_template_and_clone(
            context, id, destination, update_resources=update_resources,
            sys_clone=sys_clone)
