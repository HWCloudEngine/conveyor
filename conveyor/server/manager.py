# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from conveyor import manager
from conveyor.server import rpcapi
from conveyor import volume

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class MigrationManager(manager.Manager):
    """Manages the running instances from creation to destruction."""

    target = messaging.Target(version='3.40')

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        self.volume_api = volume.API()
        self._last_host_check = 0
        self._last_bw_usage_poll = 0
        self._bw_usage_supported = True
        self._last_bw_usage_cell_update = 0
        self.migration_rpcapi = rpcapi.MigrationAPI()

        self._resource_tracker_dict = {}
        self._syncs_in_progress = {}

        super(MigrationManager, self).\
            __init__(service_name="conveyor-migration", *args, **kwargs)

    def get_all(self, context):
        LOG.debug("MigrationManager get all start")
        return
