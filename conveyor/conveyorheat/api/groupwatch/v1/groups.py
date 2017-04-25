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


class GroupController(object):
    """WSGI controller for Groups in GroupWatch v1 API.

    Implements the API actions
    """
    # Define request scope (must match what is in policy.json)
    REQUEST_SCOPE = 'groupwatch_groups'

    def __init__(self, options):
        self.options = options
        self.group_controller = service.GroupController()

    @util.policy_enforce
    def create(self, req, body):
        gp = self.group_controller.create_group(req.context,
                                                body.get('id'),
                                                body.get('name'),
                                                body.get('type'),
                                                body.get('data'),
                                                body.get('members'))
        return {'group': format(req, gp)}

    @util.policy_enforce
    def index(self, req):
        """Lists summary information for all Groups."""

        gps = self.group_controller.list_group(req.context)
        return {
            'groups': [format(req, a) for a in gps]
        }

    @util.policy_enforce
    def show(self, req, group_id):
        """Gets detailed information for a group."""
        gp = self.group_controller.show_group(req.context, group_id)
        return {'group': format(req, gp)}

    @util.policy_enforce
    def update(self, req, group_id, body):
        gp = self.group_controller.update_group(
            req.context,
            group_id,
            body.get('name'),
            body.get('type'),
            body.get('data'),
            body.get('members')
        )

        return {'group': format(req, gp)}

    @util.policy_enforce
    def delete(self, req, group_id):
        return self.group_controller.delete_group(req.context, group_id)

    @util.policy_enforce
    def member_create(self, req, body):
        # Not implement
        raise exc.HTTPNotImplemented()

    @util.policy_enforce
    def member_index(self, req, member_id):
        # Not implement
        raise exc.HTTPNotImplemented()

    @util.policy_enforce
    def member_delete(self, req, member_id):
        # Not implement
        raise exc.HTTPNotImplemented()


def create_resource(options):
    """Resources resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = serializers.JSONResponseSerializer()
    return wsgi.Resource(GroupController(options), deserializer, serializer)
