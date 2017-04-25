# Copyright (c) 2014, Huawei Technologies Co., Ltd
# All rights reserved.

from conveyor.conveyorheat.common import short_id
from conveyor.conveyorheat.engine.resources.openstack.ceilometer import alarm
from conveyor.conveyorheat.engine import watchrule


class GroupAlarm(alarm.CeilometerAlarm):

    def handle_create(self):
        props = self.cfn_to_ceilometer(self.stack,
                                       self.parsed_template('Properties'))

        props['name'] = short_id.get_id(self.uuid)
        project_id = self.context.tenant_id
        props['project_id'] = project_id
        props['enabled'] = self.properties.get('enabled', True)

        group_rule = props['group_rule']
        group_rule['threshold_level'] = {'Warning': group_rule['threshold']}
        del group_rule['threshold']

        meter_name = self.properties.get(self.METER_NAME, None)
        if "inst.state" == meter_name:
            query = group_rule.get('query', [])
            query.append(dict(field='project_id', op='eq', value=project_id))
            group_rule['query'] = query
        alarm = self.ceilometer().alarms.create(**props)
        self.resource_id_set(alarm.alarm_id)

        # the watchrule below is for backwards compatibility.
        # 1) so we don't create watch tasks unneccessarly
        # 2) to support CW stats post, we will redirect the request
        #    to ceilometer.
        wr = watchrule.WatchRule(context=self.context,
                                 watch_name=self.physical_resource_name(),
                                 rule=self.parsed_template('Properties'),
                                 stack_id=self.stack.id)
        wr.state = wr.CEILOMETER_CONTROLLED
        wr.store()

    def cfn_to_ceilometer(self, stack, properties):
        kwargs = super(GroupAlarm, self).cfn_to_ceilometer(stack, properties)
        kwargs['type'] = 'group'
        kwargs['group_rule'] = kwargs['threshold_rule']
        del kwargs['threshold_rule']
        return kwargs


def resource_mapping():
    return {
        'Huawei::FusionSphere::GroupAlarm': GroupAlarm,
    }
