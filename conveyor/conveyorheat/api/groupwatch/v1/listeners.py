from oslo_log import log as logging

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common import serializers
from conveyor.conveyorheat.common import wsgi
from conveyor.conveyorheat.engine.groupwatch import service

LOG = logging.getLogger(__name__)


class ListenerController(object):
    """WSGI controller for Resources in GroupWatch v1 API.

    Implements the API actions
    """
    # Define request scope (must match what is in policy.json)
    REQUEST_SCOPE = 'groupwatch_listeners'

    LISTENER_IDS = (
        CES, SCHEDULER
    ) = (
        'ces', 'scheduler'
    )

    def __init__(self, options):
        self.options = options
        self.task_controller = service.TaskManager()
        self.alarm_controller = service.AlarmController()

    def signal(self, req, listener_id, body):
        """Handle signal.

        :param req:
        :param listener_id:
        :param body:
        :return:
        """
        if listener_id not in self.LISTENER_IDS:
            LOG.error('listener id (%s) is invalid.' % listener_id)
            return

        if listener_id == self.CES:
            alarm_id = body.get('alarm_id')
            alarm_status = body.get('alarm_status')
            LOG.info('ces signal: alarm_id %s. alarm status %s'
                     % (alarm_id, alarm_status))

            return self.alarm_controller.signal(req.context,
                                                alarm_id,
                                                alarm_status)
        elif listener_id == self.SCHEDULER:
            job_name = body.get('job_name')
            metadata = body.get('meta_data')

            LOG.info('scheduler signal: job name %s, metadata %s'
                     % (job_name, metadata))
            group_id = metadata.get('group_id') if metadata else None
            return self.task_controller.signal(req.context, group_id)
        else:
            LOG.error('Listener id (%s) is not found.' % listener_id)
            raise exception.ValidationError()


def create_resource(options):
    """Resources resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = serializers.JSONResponseSerializer()
    return wsgi.Resource(ListenerController(options), deserializer, serializer)
