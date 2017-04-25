# Copyright (c) 2014, Huawei Technologies Co., Ltd
# All rights reserved.

from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.openstack.ceilometer import alarm
from conveyor.conveyorheat.engine import watchrule


class CeilometerAlarm(alarm.CeilometerAlarm):
    PROPERTIES = (
        COMPARISON_OPERATOR, EVALUATION_PERIODS, METER_NAME, PERIOD,
        STATISTIC, THRESHOLD, MATCHING_METADATA, AVAILABILITY_ZONE,
    ) = (
        'comparison_operator', 'evaluation_periods', 'meter_name', 'period',
        'statistic', 'threshold', 'matching_metadata', 'availability_zone',
    )

    properties_schema = {
        AVAILABILITY_ZONE: properties.Schema(
            properties.Schema.STRING,
            _('Name of the availability zone for alarm placement.'),
            update_allowed=False
        )
    }

    properties_schema.update(alarm.CeilometerAlarm.properties_schema)

    def handle_create(self):
        props = self.cfn_to_ceilometer(self.stack,
                                       self.properties)

        if (self.AVAILABILITY_ZONE in props.keys()
                and props[self.AVAILABILITY_ZONE]):
            # Fill availability zone into alarm request if exist in properties.
            # availability zone is optional, so if not exist in properties, we
            # will not set it into metadata.
            value = props[self.AVAILABILITY_ZONE]
            if 'matching_metadata' in props.keys():
                props['matching_metadata'].update(
                    {'metadata.metering.region': value}
                )
            else:
                props['matching_metadata'] =\
                    {'metadata.metering.region': value}

            props.pop(self.AVAILABILITY_ZONE)

        props['name'] = self.physical_resource_name()
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


def resource_mapping():
    return {
        'Huawei::FusionSphere::Alarm': CeilometerAlarm,
    }
