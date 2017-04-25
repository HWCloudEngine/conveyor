import functools

from oslo_service import threadgroup

from conveyor.conveyorheat.common import context
from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine import clients
from conveyor.conveyorheat.engine.groupwatch import alarm
from conveyor.conveyorheat.engine.groupwatch import group
from conveyor.conveyorheat.engine.groupwatch import task


def request_context(func):
    @functools.wraps(func)
    def wrapped(self, ctx, *args, **kwargs):
        if ctx is not None and not isinstance(ctx, context.RequestContext):
            ctx = context.RequestContext.from_dict(ctx.to_dict())
        try:
            return func(self, ctx, *args, **kwargs)
        except exception.HeatException:
            raise
    return wrapped


def alarm_transform(alm):
    ret = {
        'id': alm.id,
        'resource_id': alm.resource_id,
        'group_id': alm.group_id,
        'meter_name': alm.meter_name,
        'data': alm.data,
        'actions': alm.actions,
        'tenant': alm.tenant,
        'user': alm.user,
        'created_time': alm.created_time,
        'updated_time': alm.updated_time
    }

    return ret


class AlarmController(object):

    def __init__(self):
        super(AlarmController, self).__init__()
        self.tg = threadgroup.ThreadGroup()

    @request_context
    def create_alarm(self, ctxt, alarm_id, group_id, meter_name,
                     metadata, actions):

        alm = alarm.Alarm(ctxt, alarm_id, group_id, meter_name,
                          metadata, actions)

        alm.store()

        return alarm_transform(alm)

    @request_context
    def list_alarm(self, ctxt, limit=None, marker=None, sort_keys=None,
                   sort_dir=None, filters=None, tenant_safe=True):

        alms = []
        for a in alarm.Alarm.load_all(ctxt):
            alms.append(alarm_transform(a))
        return alms

    @request_context
    def show_alarm(self, ctxt, alarm_id):

        alm = alarm.Alarm.load(ctxt, alarm_id)
        return alarm_transform(alm)

    @request_context
    def delete_alarm(self, ctxt, alarm_id):

        alm = alarm.Alarm.load(ctxt, alarm_id)
        alm.delete()

    @request_context
    def update_alarm(self, ctxt, alarm_id, group_id, meter_name,
                     metadata, actions):

        alm = alarm.Alarm.load(ctxt, alarm_id)
        alm.update(group_id, meter_name, metadata, actions)

        return alarm_transform(alm)

    @request_context
    def signal(self, ctxt, alarm_id, alarm_status):
        alm = alarm.Alarm.load(ctxt, alarm_id)
        self.tg.add_thread(alm.signal)


class GroupController(object):
    def __init__(self):
        super(GroupController, self).__init__()

    @request_context
    def create_group(self, ctxt, group_id, name, type, data, members={}):
        gp = group.Group(ctxt, group_id, name, type, data, members)
        gp.create()

        return gp.to_dict()

    @request_context
    def delete_group(self, ctxt, group_id):
        gp = group.Group.load(ctxt, group_id)
        gp.delete()

    @request_context
    def update_group(self, ctxt, group_id, name, type, data, members):
        gp = group.Group.load(ctxt, group_id)
        update_data = {}
        if type:
            update_data.update({"type": type})

        if members:
            update_data.update({"members": members})

        if data:
            update_data.update({"data": data})

        gp.update(group_id, **update_data)

        return gp.to_dict()

    @request_context
    def show_group(self, ctxt, group_id):
        gp = group.Group.load(ctxt, group_id)
        return gp.to_dict()

    @request_context
    def list_group(self, ctxt):
        gps = []
        for gp in group.Group.load_all(ctxt):
            gps.append(gp.to_dict())
        return gps

    @request_context
    def create_member(self):
        raise exception.NotSupported()

    @request_context
    def list_member(self):
        raise exception.NotSupported()

    @request_context
    def delete_member(self):
        raise exception.NotSupported()


class TaskManager(object):
    def __init__(self):
        super(TaskManager, self).__init__()
        clients.initialise()

    @request_context
    def signal(self, ctxt, group_id):
        t = task.Task(ctxt, group_id)
        t.signal()
