from oslo_log import log as logging
import requests

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.db import api as db_api

LOG = logging.getLogger(__name__)


class Alarm(object):
    def __init__(self, context, alarm_id, group_id, meter_name,
                 data=None, actions=None, tenant=None, user=None,
                 created_time=None, updated_time=None):
        self.id = alarm_id
        self.resource_id = alarm_id
        self.context = context
        self.group_id = group_id
        self.meter_name = meter_name
        self.actions = actions
        self.data = data
        self.tenant = tenant or self.context.tenant_id
        self.user = user or self.context.user_id
        self.created_time = created_time
        self.updated_time = updated_time

    def store(self):
        alm = {
            'id': self.id,
            'resource_id': self.resource_id,
            'group_id': self.group_id,
            'meter_name': self.meter_name,
            'actions': self.actions,
            'data': self.data,
            'tenant': self.tenant,
            'user': self.user
        }

        stored_alm = db_api.gw_alarm_create(self.context, alm)
        self.id = stored_alm.id
        self.created_time = stored_alm.created_at

    def create(self):
        self.store()

    def delete(self):
        db_api.gw_alarm_delete(self.context, self.id)

    def update(self, group_id, meter_name, metadata, actions):
        values = {
            'group_id': group_id,
            'meter_name': meter_name,
            'data': metadata,
            'actions': actions
        }

        # FIXME: once update fails, we should rollback groupwatch
        db_api.gw_alarm_update(self.context, self.id, values)

        self.group_id = group_id
        self.meter_name = meter_name
        self.data = metadata

    @classmethod
    def load(cls, context, alarm_id=None, alarm=None, show_deleted=True):
        if alarm is None:
            alarm = db_api.gw_alarm_get(context, alarm_id,
                                        show_deleted=show_deleted)

        if alarm is None:
            message = _('No alarm exists with id "%s"') % str(alarm_id)
            raise exception.NotFound(message)

        return cls._from_db(context, alarm)

    @classmethod
    def load_all(cls, context, limit=None, marker=None, sort_keys=None,
                 sort_dir=None, filters=None, tenant_safe=True):
        alarms = db_api.gw_alarm_get_all(context, limit, sort_keys, marker,
                                         sort_dir, filters, tenant_safe) or []
        for alarm in alarms:
            yield cls._from_db(context, alarm)

    @classmethod
    def _from_db(cls, context, alarm):
        ret = cls(context,
                  alarm.id,
                  alarm.group_id,
                  alarm.meter_name,
                  alarm.data,
                  alarm.actions,
                  alarm.tenant,
                  alarm.user,
                  alarm.created_at,
                  alarm.updated_at)
        ret.resource_id = alarm.resource_id

        return ret

    def signal(self):
        def post_action(url):
            requests.post(url, verify=False)

        try:
            alarm_actions = self.actions.get('alarm_actions')
            for action in alarm_actions:
                post_action(action)
        except Exception as ex:
            LOG.ERROR('task signal failed, exception: %s', ex)
            raise ex
