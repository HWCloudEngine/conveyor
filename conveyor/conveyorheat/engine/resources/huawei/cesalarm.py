from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine import resource

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils

LOG = logging.getLogger(__name__)


class CesAlarm(resource.Resource):

    PROPERTIES = (
        DESCRIPTION, NAME, RESOURCE_ID,
        METER_NAME, PERIOD, STATISTIC,
        COMPARISON_OPERATOR, THRESHOLD, UNIT, EVALUATION_PERIODS,
        ALARM_ACTIONS, INSUFFICIENT_DATA_ACTIONS, OK_ACTIONS,
        ENABLED, ACTION_ENABLED, MATCHING_METADATA,
    ) = (
        'description', 'name', 'resource_id',
        'meter_name', 'period', 'statistic',
        'comparison_operator', 'threshold', 'unit', 'evaluation_periods',
        'alarm_actions', 'insufficient_data_actions', 'ok_actions',
        'enabled', 'action_enabled', 'matching_metadata',
    )
    DIMENSION_KEY = 'groupwatch'

    properties_schema = {
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('Description for the alarm.'),
            required=False,
            constraints=[
                constraints.AllowedPattern(r"^[^\&\<\>\"\'\(\)]{0,256}$")
            ],
            update_allowed=True
        ),
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('Name of the alarm.'),
            required=False,
            constraints=[
                constraints.AllowedPattern(r"^[0-9a-zA-Z_-]{1,128}$")
            ],
            update_allowed=True
        ),
        RESOURCE_ID: properties.Schema(
            properties.Schema.STRING,
            _('ID of the group.'),
            required=True,
            update_allowed=False
        ),
        METER_NAME: properties.Schema(
            properties.Schema.STRING,
            _('Metric name.'),
            required=True,
            constraints=[
                constraints.AllowedPattern(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
            ],
            update_allowed=False
        ),
        PERIOD: properties.Schema(
            properties.Schema.INTEGER,
            _('Period (seconds) to evaluate over.'),
            required=True,
            constraints=[
                constraints.AllowedValues([300, 1200, 3600, 14400, 86400])
            ],
            update_allowed=True
        ),
        STATISTIC: properties.Schema(
            properties.Schema.STRING,
            _('Way to data aggregation.'),
            required=True,
            constraints=[
                constraints.AllowedValues(['avg', 'min', 'max', 'variance'])
            ],
            update_allowed=True
        ),
        COMPARISON_OPERATOR: properties.Schema(
            properties.Schema.STRING,
            _('Operator used to compare specified statistic with threshold.'),
            required=True,
            constraints=[
                constraints.AllowedValues(['gt', 'lt', 'ge', 'le', 'eq'])
            ],
            update_allowed=True
        ),
        THRESHOLD: properties.Schema(
            properties.Schema.INTEGER,
            _('Threshold value of alarm.'),
            required=True,
            update_allowed=True
        ),
        UNIT: properties.Schema(
            properties.Schema.STRING,
            _('Unit of data.'),
            required=False,
            constraints=[
                constraints.AllowedPattern(r"^.{0,32}$")
            ],
            update_allowed=True
        ),
        EVALUATION_PERIODS: properties.Schema(
            properties.Schema.INTEGER,
            _('Consecutive count.'),
            required=True,
            constraints=[
                constraints.Range(1, 5)
            ],
            update_allowed=True
        ),
        ALARM_ACTIONS: properties.Schema(
            properties.Schema.LIST,
            _('A list of URLs (webhooks) to invoke when state transitions to'
              'alarm'),
            required=False,
            update_allowed=True
        ),
        INSUFFICIENT_DATA_ACTIONS: properties.Schema(
            properties.Schema.LIST,
            _('Not Implemented.'),
            required=False,
            update_allowed=True
        ),
        OK_ACTIONS: properties.Schema(
            properties.Schema.LIST,
            _('Not Implemented.'),
            required=False,
            update_allowed=True
        ),
        ENABLED: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Whether to enable alarm.'),
            required=False,
            default=True,
            update_allowed=False
        ),
        ACTION_ENABLED: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Whether to enable this alarm to trigger actions.'),
            required=False,
            default=True,
            update_allowed=True
        ),
        MATCHING_METADATA: properties.Schema(
            properties.Schema.MAP,
            _('Meter should match this resource metadata (key=value) '
              'additionally to the meter_name.'),
            default={}
        ),
    }

    default_client_name = 'ces'

    def _translate_key(self, key):
        mapping = {
            self.NAME: 'alarm_name',
            self.DESCRIPTION: 'alarm_description',
            self.RESOURCE_ID: self.RESOURCE_ID,
            self.METER_NAME: 'metric_name',
            self.PERIOD: 'period',
            self.STATISTIC: 'filter',
            self.COMPARISON_OPERATOR: 'comparison_operator',
            self.THRESHOLD: 'value',
            self.UNIT: self.UNIT,
            self.EVALUATION_PERIODS: 'count',
            self.ALARM_ACTIONS: 'alarm_actions',
            self.INSUFFICIENT_DATA_ACTIONS: 'insufficientdata_actions',
            self.OK_ACTIONS: 'ok_actions',
            self.ENABLED: 'alarm_enabled',
            self.ACTION_ENABLED: 'alarm_action_enabled'
        }
        return mapping.get(key, None)

    def _translate_operator(self, operator):
        mapping = {
            'ge': '>=', 'gt': '>', 'eq': '=', 'lt': '<', 'le': '<='
        }
        return mapping.get(operator, None)

    def _translate_statistic(self, statistic_method):
        mapping = {
            'avg': 'average', 'min': 'min', 'max': 'max',
            'variance': 'variance'
        }

        return mapping.get(statistic_method, None)

    def _create_condition(self):
        condition = {}
        for k in [self.PERIOD, self.STATISTIC, self.COMPARISON_OPERATOR,
                  self.THRESHOLD, self.EVALUATION_PERIODS, self.UNIT]:
            v = self.properties.get(k)

            if k == self.COMPARISON_OPERATOR:
                condition['comparison_operator'] = self._translate_operator(v)
            elif k == self.STATISTIC:
                condition['filter'] = self._translate_statistic(v)
            elif v is not None:
                condition[self._translate_key(k)] = v

        return condition

    def _actions_to_urls(self):
        kwargs = {}
        for k, v in iter(self.properties.items()):
            if k in [self.ALARM_ACTIONS, self.OK_ACTIONS,
                     self.INSUFFICIENT_DATA_ACTIONS] and v is not None:
                kwargs[k] = []
                for act in v:
                    # if the action is a resource name
                    # we ask the destination resource for an alarm url.
                    # the template writer should really do this in the
                    # template if possible with:
                    # {Fn::GetAtt: ['MyAction', 'AlarmUrl']}
                    if act in self.stack:
                        url = self.stack[act].FnGetAtt('AlarmUrl')
                        kwargs[k].append(url)
                    else:
                        if act:
                            kwargs[k].append(act)
        return kwargs

    def _build_actions(self):
        return {
            'alarm_actions': [{
                'type': 'groupwatch',
                'notificationList': []
            }]
        }

    def _get_physical_resource_id(self, resource_id):
        if not resource_id:
            return None

        if uuidutils.is_uuid_like(resource_id):
            return resource_id

        ref_resource = self.stack.resource_by_refid(resource_id)
        if ref_resource:
            return ref_resource.resource_id

    def _build_metric(self):
        return {
            'namespace': 'rts.groupwatch',
            'metric_name': self.properties.get(self.METER_NAME),
            'dimensions': [{
                'name': 'groupwatch',
                'value': self._get_physical_resource_id(
                    self.properties.get(self.RESOURCE_ID)),
            }]
        }

    def _add_groupwatch_alarm(self, alarm_id):
        # If not permit using groupwatch, we will do noting.
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        kwargs = {
            'alarm_id': alarm_id,
            'resource_id': alarm_id,
            'meter_name': self.properties.get(self.METER_NAME),
            'group_id': self._get_physical_resource_id(
                self.properties.get(self.RESOURCE_ID)),
            'actions': self._actions_to_urls(),
            'data': {}
        }
        self.client('groupwatch').alarms.create(**kwargs)

    def handle_create(self):
        name = self.properties.get(self.NAME)
        if name is None or name == "":
            name = self.physical_resource_name()
        kwargs = {
            'alarm_name': name,
            'alarm_description': self.properties.get(self.DESCRIPTION) or '',
            'metric': self._build_metric(),
            'condition': self._create_condition(),
            'alarm_enabled': self.properties.get(self.ENABLED),
            'alarm_action_enabled':
                self.properties.get(self.ACTION_ENABLED)
        }

        kwargs.update(self._build_actions())
        alarm = self.client('ces').alarms.create(**kwargs)

        self.resource_id_set(alarm['alarm_id'])

        self._add_groupwatch_alarm(alarm['alarm_id'])

    def _update_condition(self, prop_diff):
        condition = {}
        for k in [self.PERIOD, self.STATISTIC, self.COMPARISON_OPERATOR,
                  self.THRESHOLD, self.EVALUATION_PERIODS, self.UNIT]:
            v = prop_diff.get(k) or self.properties.get(k)

            if k == self.COMPARISON_OPERATOR:
                condition['comparison_operator'] = self._translate_operator(v)
            elif k == self.STATISTIC:
                condition['filter'] = self._translate_statistic(v)
            elif v is not None:
                condition[self._translate_key(k)] = v

        return condition

    def _update_groupwatch_alarm(self, alarm_id, prop_diff):
                # If not permit using groupwatch, we will do noting.
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        kwargs = {
            'alarm_id': alarm_id,
            'resource_id': alarm_id,
            'meter_name': self.properties.get(self.METER_NAME),
            'group_id': self._get_physical_resource_id(
                self.properties.get(self.RESOURCE_ID)),
            'actions': self._actions_to_urls(),
        }
        self.client('groupwatch').alarms.update(**kwargs)

    def handle_update(self, json_snippet=None, tmpl_diff=None, prop_diff=None):
        checkers = {}
        if prop_diff:
            checkers.update({
                'alarm_description': (prop_diff.get(self.DESCRIPTION) or
                                      self.properties.get(self.DESCRIPTION)),
                'condition': self._update_condition(prop_diff),
                'alarm_action_enabled':
                    (prop_diff.get(self.ACTION_ENABLED) or
                     self.properties.get(self.ACTION_ENABLED))
            })

            if prop_diff.get(self.NAME):
                checkers.update({'alarm_name': prop_diff.get(self.NAME)})

            if checkers:
                self.client('ces').alarms.update(
                    self.resource_id,
                    **checkers
                )

        self._update_groupwatch_alarm(self.resource_id, prop_diff)

    def handle_suspend(self):
        tenant_id = self.stack.stack_user_project_id
        alarm_id = self.resource_id
        if alarm_id is not None and tenant_id is not None:
            self.client('ces').alarms.suspend(alarm_id)

    def handle_resume(self):
        tenant_id = self.stack.stack_user_project_id
        alarm_id = self.resource_id
        if alarm_id is not None and tenant_id is not None:
            self.client('ces').alarm.resume(alarm_id)

    def _delete_scheduler(self, scheduler_task_id):
        if not scheduler_task_id:
            return

        try:
            self.client('scheduler').scheduler.delete(scheduler_task_id)
        except Exception as ex:
            self.client_plugin('scheduler').ignore_not_found(ex)

    def _delete_groupwatch_alarm(self, resource_id):
        # If not permit using groupwatch, we will do noting.
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        if not resource_id:
            return

        # try:
        #     self.client('groupwatch').alarms.delete(resource_id)
        # except Exception as ex:
        #     self.client_plugin('groupwatch').ignore_not_found(ex)

    def handle_delete(self):
        if self.resource_id is not None:
            self._delete_groupwatch_alarm(self.resource_id)
            # try:
            #     self.client('ces').alarms.delete(self.resource_id)
            # except Exception as ex:
            #     self.client_plugin().ignore_not_found(ex)


def resource_mapping():
    return {
        'OSE::CES::Alarm': CesAlarm,
    }
