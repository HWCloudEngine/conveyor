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

import routes

from conveyor.conveyorheat.api.groupwatch.v1 import alarms
from conveyor.conveyorheat.api.groupwatch.v1 import groups
from conveyor.conveyorheat.api.groupwatch.v1 import listeners
from conveyor.conveyorheat.api.groupwatch.v1 import tasks
from conveyor.conveyorheat.common import wsgi


class API(wsgi.Router):

    """WSGI router for Groupwatch v1 ReST API requests."""

    def __init__(self, conf, **local_conf):
        self.conf = conf
        mapper = routes.Mapper()

        # Alarms
        alarms_resource = alarms.create_resource(conf)
        with mapper.submapper(controller=alarms_resource,
                              path_prefix="/{tenant_id}") as alarm_mapper:

            alarm_mapper.connect("alarm_create",
                                 "/alarms",
                                 action="create",
                                 conditions={'method': 'POST'})

            alarm_mapper.connect("alarm_list",
                                 "/alarms",
                                 action="index",
                                 conditions={'method': 'GET'})

            alarm_mapper.connect("alarm_update",
                                 "/alarms/{alarm_id}",
                                 action="update",
                                 conditions={'method': 'PUT'})

            alarm_mapper.connect("alarm_update_patch",
                                 "/stacks/{alarm_id}",
                                 action="update_patch",
                                 conditions={'method': 'PATCH'})

            alarm_mapper.connect("alarm_show",
                                 "/alarms/{alarm_id}",
                                 action="show",
                                 conditions={'method': 'GET'})

            alarm_mapper.connect("alarm_delete",
                                 "/alarms/{alarm_id}",
                                 action="delete",
                                 conditions={'method': 'DELETE'})

        # Groups
        groups_resource = groups.create_resource(conf)
        with mapper.submapper(controller=groups_resource,
                              path_prefix="/{tenant_id}") as group_mapper:

            group_mapper.connect("group_create",
                                 "/groups",
                                 action="create",
                                 conditions={'method': 'POST'})

            group_mapper.connect("group_list",
                                 "/groups",
                                 action="index",
                                 conditions={'method': 'GET'})

            group_mapper.connect("group_update",
                                 "/groups/{group_id}",
                                 action="update",
                                 conditions={'method': 'PUT'})

            group_mapper.connect("group_show",
                                 "/groups/{group_id}",
                                 action="show",
                                 conditions={'method': 'GET'})

            group_mapper.connect("group_delete",
                                 "/groups/{group_id}",
                                 action="delete",
                                 conditions={'method': 'DELETE'})

            group_mapper.connect("member_create",
                                 "/groups/{group_id}/members",
                                 action="member_create",
                                 conditions={'method': 'POST'})

            group_mapper.connect("member_list",
                                 "/groups/{group_id}/members",
                                 action="member_index",
                                 conditions={'method': 'GET'})

            group_mapper.connect("member_delete",
                                 "/groups/{group_id}/members/{member_id}",
                                 action="member_delete",
                                 conditions={'method': 'DELETE'})

        # Tasks
        tasks_resource = tasks.create_resource(conf)
        with mapper.submapper(controller=tasks_resource,
                              path_prefix="/{tenant_id}") as task_mapper:

            task_mapper.connect("task_create",
                                "/tasks",
                                action="create",
                                conditions={'method': 'POST'})

            task_mapper.connect("task_list",
                                "/tasks",
                                action="index",
                                conditions={'method': 'GET'})

            task_mapper.connect("task_update",
                                "/tasks/{task_id}",
                                action="update",
                                conditions={'method': 'PUT'})

            task_mapper.connect("task_update_patch",
                                "/tasks/{task_id}",
                                action="update_patch",
                                conditions={'method': 'PATCH'})

            task_mapper.connect("task_show",
                                "/tasks/{task_id}",
                                action="show",
                                conditions={'method': 'GET'})

            task_mapper.connect("task_delete",
                                "/tasks/{task_id}",
                                action="delete",
                                conditions={'method': 'DELETE'})

            task_mapper.connect("task_signal",
                                "/tasks/{task_id}",
                                action="signal",
                                conditions={'method': 'POST'})

        # Listeners
        listeners_res = listeners.create_resource(conf)
        with mapper.submapper(controller=listeners_res) as listener_mapper:
            listener_mapper.connect("listener_signal",
                                    "/listeners/{listener_id}",
                                    action="signal",
                                    conditions={'method': 'POST'})

        super(API, self).__init__(mapper)
