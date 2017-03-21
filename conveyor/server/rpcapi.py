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
import oslo_messaging as messaging
from oslo_serialization import jsonutils
from oslo_log import log as logging

from conveyor import rpc


CONF = cfg.CONF

LOG = logging.getLogger(__name__)

class MigrationAPI(object):
    '''Client side of the volume rpc API.

    API version history:

        1.0 - Initial version.
    '''

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic=None):
        super(MigrationAPI, self).__init__()
        target = messaging.Target(topic=CONF.volume_topic,
                                  version=self.BASE_RPC_API_VERSION)
        self.client = rpc.get_client(target, '1.23', serializer=None)

    def get_all(self, ctxt, host):
        
        LOG.debug("migration rpc api start")
        new_host = host
        cctxt = self.client.prepare(server=new_host, version='1.18')
        cctxt.cast(ctxt, 'get_all')



