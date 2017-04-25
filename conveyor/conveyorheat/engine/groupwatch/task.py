import time

from oslo_log import log as logging
from oslo_service import threadgroup

from conveyor.db import api as db_api

LOG = logging.getLogger(__name__)


class Task(object):
    def __init__(self, context, group_id):
        self.context = context
        self.group_id = group_id
        self.thread_group = threadgroup.ThreadGroup()

    def _get_alarms(self):
        alarms = db_api.gw_alarm_get_all_by_group(self.context, self.group_id)
        return alarms

    def _get_members(self):
        members = db_api.gw_member_get_all_by_group(self.context,
                                                    self.group_id)
        return [member.id for member in members]

    def _get_metric_data(self, instance_id, metric_name):
        # milliseconds of current time
        cur_mm = int(time.time() * 1000)
        kwargs = {
            'namespace': 'SYS.ECS',
            'to': cur_mm,
            # start time is 8 minutes backward of current time
            'from': cur_mm - 8 * 60 * 1000,
            'metric_name': metric_name,
            'period': 1,
            'filter': 'average',
            'dimensions': [{
                'name': 'instance_id',
                'value': instance_id
            }]
        }

        metrics = self.ces_client().metrics.get(**kwargs)
        return metrics[0] if metrics else []

    def _do_calculate(self, members, metric_name):
        LOG.debug('calculate metric: %s members: %s' % (metric_name, members))
        metric_data = []
        for member in members:
            data = self._get_metric_data(member, metric_name)
            if data:
                metric_data.append(data)

        LOG.info('get metric data from ces, data: %s', metric_data)
        if not metric_data:
            # no metric data for current caculate.
            LOG.info('no metric data found, return')
            return

        avg = sum(data['average'] for data in metric_data) / len(metric_data)
        calculated_data = [{"metric": {
            'namespace': 'rts.groupwatch',
            'metric_name': metric_name,
            'dimensions': [{
                'name': 'groupwatch',
                'value': self.group_id
            }]},
            'ttl': 604800,
            'collect_time': int(time.time() * 1000),
            'value': avg,
            'unit': metric_data[0]['unit']
        }]
        LOG.debug('creating metrics: %s', calculated_data)
        self.ces_client().metrics.create(calculated_data)

        LOG.debug('calculate metric end')

    def calculate_metrics(self):

        def calculate(*args):
            try:
                self._do_calculate(*args)
            except Exception as ex:
                LOG.error('calculate metrics failed, exception: %s', ex)

        LOG.debug("start calculate metrics, group_id %s", self.group_id)
        alarms = self._get_alarms()
        LOG.debug("get all alarms: %s", alarms)
        members = self._get_members()
        LOG.debug("get all members: %s", members)
        meters = []
        for alm in alarms:
            if alm.meter_name not in meters:
                meters.append(alm.meter_name)

        LOG.debug("processing group tasks, meters: %s", meters)
        for meter in meters:
            self.thread_group.add_thread(calculate,
                                         members,
                                         meter)
        LOG.debug('task signal end')

    def signal(self):
        self.calculate_metrics()

    def ces_client(self):
        return self.context.clients.client('ces')
