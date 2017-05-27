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
from oslo_utils import importutils

from conveyor.clone.resources import common
from conveyor.i18n import _LW
from conveyor.resource import api as resource_api

from conveyor import exception

migrate_manager_opts = [
    cfg.StrOpt('volume_clone_driver',
               default='conveyor.clone.resources.volume.'
                       'driver.volume.VolumeCloneDriver',
               help='volume clone driver')
]


CONF = cfg.CONF
CONF.register_opts(migrate_manager_opts)
LOG = logging.getLogger(__name__)


class CloneManager(object):
    """Manages the running instances from creation to destruction."""
    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        self.clone_driver = importutils.import_object(CONF.volume_clone_driver)
        self.resource_common = common.ResourceCommon()
        self.resource_api = resource_api.ResourceAPI()

    def _set_plan_statu(self, context, plan_id, status, state_map):
        plan_state = state_map.get(status)
        values = {}
        values['plan_status'] = plan_state
        values['task_status'] = status
        self.resource_api.update_plan(context, plan_id, values)

    def start_template_clone(self, context, resource_name, template):

        if not template:
            LOG.error("Resources in template is null")
            raise exception.V2vException(message='Template is null')

        try:
            trans_data_wait_fun = \
                self.resource_common._await_data_trans_status
            self.clone_driver.start_volume_clone(
                context, resource_name, template,
                volume_wait_fun=self.resource_common._await_volume_status,
                trans_data_wait_fun=trans_data_wait_fun,
                set_plan_state=self._set_plan_statu)
        except Exception as e:
            LOG.error(_LW("Clone volume error: %s"), e)
            _msg = 'Volume clone error: %s' % e
            raise exception.V2vException(message=_msg)
