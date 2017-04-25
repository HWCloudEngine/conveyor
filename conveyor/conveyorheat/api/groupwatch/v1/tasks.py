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


from conveyor.conveyorheat.api.groupwatch.v1 import util
from conveyor.conveyorheat.common import serializers
from conveyor.conveyorheat.common import wsgi


class TaskController(object):
    """WSGI controller for Resources in GroupWatch v1 API

    Implements the API actions
    """
    # Define request scope (must match what is in policy.json)
    REQUEST_SCOPE = 'groupwatch_tasks'

    def __init__(self, options):
        self.options = options

    @util.policy_enforce
    def index(self, req):
        """Lists summary information for all tasks."""

        return {'tasks': 'empty'}

    @util.policy_enforce
    def show(self, req):
        """Gets detailed information for a task."""
        return {'tasks': 'show empty'}


def create_resource(options):
    """Resources resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = serializers.JSONResponseSerializer()
    return wsgi.Resource(TaskController(options), deserializer, serializer)
