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

from conveyor import exception

migrate_manager_opts = [
    cfg.StrOpt('instance_clone_driver',
               default='conveyor.clone.resources.instance.'
                       'driver.stack_template.StackTemplateCloneDriver',
               help='clone driver')
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
        self.clone_driver = \
            importutils.import_object(CONF.instance_clone_driver)
        self.resource_common = common.ResourceCommon()

    def start_template_clone(self, context, resource_name, instance, copy_data):

        # 1 Traverse the list of resource, cloning every instance
        if not instance:
            LOG.error("Resources in template is null")

        # 2 set resource info according to template topo
        # (if the value of key links to other, here must set again)
        try:
            create_instance_wait_fun = \
                self.resource_common._await_instance_create
            trans_data_wait_fun = \
                self.resource_common._await_data_trans_status
            create_volume_wait_fun = \
                self.resource_common._await_block_device_map_created
            self.clone_driver.start_template_clone(
                context, resource_name, instance,
                create_volume_wait_fun=create_volume_wait_fun,
                volume_wait_fun=self.resource_common._await_volume_status,
                create_instance_wait_fun=create_instance_wait_fun,
                port_wait_fun=self.resource_common._await_port_status,
                trans_data_wait_fun=trans_data_wait_fun, copy_data=copy_data)

        except Exception as e:
            LOG.error(_LW("Clone vm error: %s"), e)
            _msg = 'Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)

    def start_template_migrate(self, context, resource_name, instance):

        if not instance:
            LOG.error("Resources in template is null")

        # (if the value of key links to other, here must set again)
        try:
            trans_data_wait_fun = \
                self.resource_common._await_data_trans_status
            self.clone_driver.start_template_migrate(
                context, resource_name, instance,
                port_wait_fun=self.resource_common._await_port_status,
                trans_data_wait_fun=trans_data_wait_fun)
        except Exception as e:
            LOG.error(_LW("Migrate vm error: %s"), e)
            _msg = 'Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)
