# Copyright (c) 2014, Huawei Technologies Co., Ltd
# All rights reserved.

from conveyor.conveyorheat.engine.resources.aws.ec2 import instance as aws_instance
from conveyor.conveyorheat.engine import scheduler
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class Instance(aws_instance.Instance):

    def handle_delete(self):
        """Delete the instance.

        The port should be deleted at the final step, or the qbr which is
        created when the port is attached to the server won't be deleted
        """
        # make sure to delete the port which implicit-created by heat

        if self.resource_id is None:
            return
        try:
            server = self.nova().servers.get(self.resource_id)
        except Exception as e:
            self.client_plugin().ignore_not_found(e)
            return
        deleters = (
            scheduler.TaskRunner(self._detach_volumes_task()),
            scheduler.TaskRunner(self.client_plugin().delete_server,
                                 server),
            scheduler.TaskRunner(self._port_data_delete))
        deleters[0].start()
        return deleters


def resource_mapping():
    return {
        'Huawei::FusionSphere::Instance': Instance
    }
