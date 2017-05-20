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

from oslo_log import log as logging

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.db import api as db_api

LOG = logging.getLogger(__name__)


class Group(object):
    def __init__(self, context, group_id, name, group_type=None,
                 data=None, members=None, tenant=None, user=None,
                 created_time=None, updated_time=None):
        self.id = group_id
        self.name = name
        self.type = group_type
        self.context = context
        self.data = data
        self.members = members
        self.tenant = tenant or self.context.tenant_id
        self.user = user or self.context.user_id
        self.created_time = created_time
        self.updated_time = updated_time

    def store(self):
        group = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'data': self.data,
            'tenant': self.tenant,
            'user': self.user,
            'created_time': self.created_time
        }

        stored_group = db_api.gw_group_create(self.context, group)
        self.id = stored_group.id
        self.created_time = stored_group.created_at

    def create(self):
        self.store()
        if self.members:
            for member in self.members:
                db_api.gw_member_create(
                    self.context,
                    {
                        'id': member.get('id'),
                        'group_id': self.id,
                        'name': member.get('name')
                    })

    def delete(self):
        db_api.gw_group_delete(self.context, self.id)

    def update(self, group_id, **kwargs):
        kwargs.pop('id', None)
        members = kwargs.pop('members', {})
        db_api.gw_group_update(self.context, group_id, kwargs)

        # delete members in
        db_api.gw_member_delete_by_group_id(self.context, group_id)
        if members:
            for member in members:
                db_api.gw_member_create(
                    self.context,
                    {
                        'id': member.get('id'),
                        'group_id': self.id,
                        'name': member.get('name')
                    })

        self.name = kwargs.get('name')
        self.type = kwargs.get('type')
        self.data = kwargs.get('data')
        self.members = members

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'data': self.data,
            'tenant': self.tenant,
            'member': self.members,
            'created_time': self.created_time
        }

    @classmethod
    def load(cls, context, group_id):
        gp = db_api.gw_group_get(context, group_id)

        if gp is None:
            message = _('No group exists with id "%s"') % str(group_id)
            raise exception.NotFound(message)

        return cls._from_db(context, gp)

    @classmethod
    def load_all(cls, context):
        gps = db_api.gw_group_get_all(context) or []
        for gp in gps:
            yield cls._from_db(context, gp)

    @classmethod
    def _from_db(cls, context, gp):
        return cls(context, gp.id, gp.name, gp.type, gp.data,
                   tenant=gp.tenant)
