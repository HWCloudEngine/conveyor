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

"""
Client side of the conveyor RPC API.
"""

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from conveyor import rpc


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class CloneAPI(object):
    '''Client side of the volume rpc API.

    API version history:

        1.0 - Initial version.
    '''

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic=None):
        super(CloneAPI, self).__init__()
        target = messaging.Target(topic=CONF.birdie_topic,
                                  version=self.BASE_RPC_API_VERSION)
        self.client = rpc.get_client(target, '1.23', serializer=None)

    def start_template_clone(self, ctxt, template):
        LOG.debug("Clone template start in Clone rpcapi mode")
        cctxt = self.client.prepare(version='1.18')
        cctxt.cast(ctxt, 'start_template_clone', template=template)

    def export_clone_template(self, ctxt, id, sys_clone, copy_data):
        LOG.debug("start call rpc api export_clone_template")
        cctxt = self.client.prepare(version='1.18')
        cctxt.cast(ctxt, 'export_clone_template', id=id, sys_clone=sys_clone,
                   copy_data=copy_data)

    def clone(self, ctxt, plan_id, az_map, clone_resources,
              clone_links, update_resources, replace_resources,
              sys_clone, data_copy):
        cctxt = self.client.prepare(version='1.18')
        cctxt.cast(ctxt, 'clone', plan_id=plan_id, az_map=az_map,
                   clone_resources=clone_resources,
                   clone_links=clone_links,
                   update_resources=update_resources,
                   replace_resources=replace_resources,
                   sys_clone=sys_clone,
                   data_copy=data_copy)

    def export_migrate_template(self, ctxt, id):
        LOG.debug("start call rpc api export_migrate_template")
        cctxt = self.client.prepare(version='1.18')
        cctxt.cast(ctxt, 'export_migrate_template', id=id)

    def migrate(self, ctxt, id, destination):
        LOG.debug("start call rpc api migrate")
        cctxt = self.client.prepare(version='1.18')
        cctxt.cast(ctxt, 'migrate', id=id, destination=destination)

    def download_template(self, ctxt, id):
        LOG.debug("start call rpc api download_template")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(ctxt, 'download_template', plan_id=id)

    def export_template_and_clone(self, ctxt, id, destination,
                                  update_resources,
                                  sys_clone=False,
                                  copy_data=True):
        LOG.debug("start call rpc api export_template_and_clone")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(ctxt, 'export_template_and_clone', id=id,
                          destination=destination,
                          update_resources=update_resources,
                          sys_clone=sys_clone,
                          copy_data=copy_data)
