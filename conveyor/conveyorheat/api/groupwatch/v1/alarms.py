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

import itertools
from webob import exc

from conveyor.conveyorheat.api.groupwatch.v1 import util
from conveyor.conveyorheat.common import serializers
from conveyor.conveyorheat.common import wsgi

from conveyor.conveyorheat.engine.groupwatch import service


def format(req, res, keys=None):
    keys = keys or []
    include_key = lambda k: k in keys if keys else True

    def transform(key, value):
        if not include_key(key):
            return

        yield (key, value)

    return dict(itertools.chain.from_iterable(
        transform(k, v) for k, v in res.items()))


class AlarmController(object):
    """WSGI controller for Resources in GroupWatch v1 API.

    Implements the API actions
    """
    # Define request scope (must match what is in policy.json)
    REQUEST_SCOPE = 'groupwatch_alarms'

    def __init__(self, options):
        self.options = options
        self.alarm_controller = service.AlarmController()

    @util.policy_enforce
    def index(self, req):
        """Lists summary information for all alarms."""
        alms = self.alarm_controller.list_alarm(req.context)
        alarms = [format(req, a) for a in alms]
        return {'alarms': alarms}

    @util.policy_enforce
    def show(self, req, alarm_id):
        """Gets detailed information for a alarm."""
        alm = self.alarm_controller.show_alarm(req.context, alarm_id)
        return {'alarm': format(req, alm)}

    @util.policy_enforce
    def create(self, req, body):
        """Create a new alarm."""
        a = self.alarm_controller.create_alarm(req.context,
                                               body.get('alarm_id'),
                                               body.get('group_id'),
                                               body.get('meter_name'),
                                               body.get('data'),
                                               body.get('actions'))
        return {'alarm': format(req, a)}

    @util.policy_enforce
    def delete(self, req, alarm_id):
        """Delete the specified alarm."""
        self.alarm_controller.delete_alarm(req.context, alarm_id)

    @util.policy_enforce
    def update(self, req, alarm_id, body):
        if 'alarm_id' in body:
            raise exc.HTTPNotFound()

        alm = self.alarm_controller.update_alarm(req.context,
                                                 alarm_id,
                                                 body.get('group_id'),
                                                 body.get('meter_name'),
                                                 body.get('data'),
                                                 body.get('actions'))
        return {'alarm': format(req, alm)}


def create_resource(options):
    """Alarms resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = serializers.JSONResponseSerializer()
    return wsgi.Resource(AlarmController(options), deserializer, serializer)
