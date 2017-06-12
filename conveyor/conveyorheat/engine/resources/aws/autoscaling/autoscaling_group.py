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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
import six

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common import grouputils
from conveyor.conveyorheat.engine import attributes
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import function
from conveyor.conveyorheat.engine.notification import \
    autoscaling as notification
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine import resource
from conveyor.conveyorheat.engine.resources.openstack.heat import \
    instance_group as instgrp
from conveyor.conveyorheat.engine import rsrc_defn
from conveyor.conveyorheat.engine import support
from conveyor.conveyorheat.scaling import cooldown
from conveyor.conveyorheat.scaling import scalingutil as sc_util
from conveyor.i18n import _
from conveyor.i18n import _LE
from conveyor.i18n import _LI

LOG = logging.getLogger(__name__)


class AutoScalingGroup(instgrp.InstanceGroup, cooldown.CooldownMixin):

    support_status = support.SupportStatus(version='2014.1')

    PROPERTIES = (
        AVAILABILITY_ZONES, LAUNCH_CONFIGURATION_NAME, MAX_SIZE, MIN_SIZE,
        COOLDOWN, DESIRED_CAPACITY, HEALTH_CHECK_GRACE_PERIOD,
        HEALTH_CHECK_TYPE, LOAD_BALANCER_NAMES, VPCZONE_IDENTIFIER, TAGS,
        INSTANCE_ID,
    ) = (
        'AvailabilityZones', 'LaunchConfigurationName', 'MaxSize', 'MinSize',
        'Cooldown', 'DesiredCapacity', 'HealthCheckGracePeriod',
        'HealthCheckType', 'LoadBalancerNames', 'VPCZoneIdentifier', 'Tags',
        'InstanceId',
    )

    _TAG_KEYS = (
        TAG_KEY, TAG_VALUE,
    ) = (
        'Key', 'Value',
    )

    _UPDATE_POLICY_SCHEMA_KEYS = (
        ROLLING_UPDATE
    ) = (
        'AutoScalingRollingUpdate'
    )

    _ROLLING_UPDATE_SCHEMA_KEYS = (
        MIN_INSTANCES_IN_SERVICE, MAX_BATCH_SIZE, PAUSE_TIME
    ) = (
        'MinInstancesInService', 'MaxBatchSize', 'PauseTime'
    )

    ATTRIBUTES = (
        INSTANCE_LIST,
    ) = (
        'InstanceList',
    )

    properties_schema = {
        AVAILABILITY_ZONES: properties.Schema(
            properties.Schema.LIST,
            _('Not Implemented.'),
            required=True
        ),
        LAUNCH_CONFIGURATION_NAME: properties.Schema(
            properties.Schema.STRING,
            _('The reference to a LaunchConfiguration resource.'),
            update_allowed=True
        ),
        INSTANCE_ID: properties.Schema(
            properties.Schema.STRING,
            _('The ID of an existing instance to use to '
              'create the Auto Scaling group. If specify this property, '
              'will create the group use an existing instance instead of '
              'a launch configuration.'),
            constraints=[
                constraints.CustomConstraint("nova.server")
            ]
        ),
        MAX_SIZE: properties.Schema(
            properties.Schema.INTEGER,
            _('Maximum number of instances in the group.'),
            required=True,
            update_allowed=True
        ),
        MIN_SIZE: properties.Schema(
            properties.Schema.INTEGER,
            _('Minimum number of instances in the group.'),
            required=True,
            update_allowed=True
        ),
        COOLDOWN: properties.Schema(
            properties.Schema.INTEGER,
            _('Cooldown period, in seconds.'),
            update_allowed=True
        ),
        DESIRED_CAPACITY: properties.Schema(
            properties.Schema.INTEGER,
            _('Desired initial number of instances.'),
            update_allowed=True
        ),
        HEALTH_CHECK_GRACE_PERIOD: properties.Schema(
            properties.Schema.INTEGER,
            _('Not Implemented.'),
            implemented=False
        ),
        HEALTH_CHECK_TYPE: properties.Schema(
            properties.Schema.STRING,
            _('Not Implemented.'),
            constraints=[
                constraints.AllowedValues(['EC2', 'ELB']),
            ],
            implemented=False
        ),
        LOAD_BALANCER_NAMES: properties.Schema(
            properties.Schema.LIST,
            _('List of LoadBalancer resources.')
        ),
        VPCZONE_IDENTIFIER: properties.Schema(
            properties.Schema.LIST,
            _('Use only with Neutron, to list the internal subnet to '
              'which the instance will be attached; '
              'needed only if multiple exist; '
              'list length must be exactly 1.'),
            schema=properties.Schema(
                properties.Schema.STRING,
                _('UUID of the internal subnet to which the instance '
                  'will be attached.')
            )
        ),
        TAGS: properties.Schema(
            properties.Schema.LIST,
            _('Tags to attach to this group.'),
            schema=properties.Schema(
                properties.Schema.MAP,
                schema={
                    TAG_KEY: properties.Schema(
                        properties.Schema.STRING,
                        required=True
                    ),
                    TAG_VALUE: properties.Schema(
                        properties.Schema.STRING,
                        required=True
                    ),
                },
            )
        ),
    }

    attributes_schema = {
        INSTANCE_LIST: attributes.Schema(
            _("A comma-delimited list of server ip addresses. "
              "(Heat extension)."),
            type=attributes.Schema.STRING
        ),
    }

    rolling_update_schema = {
        MIN_INSTANCES_IN_SERVICE: properties.Schema(properties.Schema.INTEGER,
                                                    default=0),
        MAX_BATCH_SIZE: properties.Schema(properties.Schema.INTEGER,
                                          default=1),
        PAUSE_TIME: properties.Schema(properties.Schema.STRING,
                                      default='PT0S')
    }

    update_policy_schema = {
        ROLLING_UPDATE: properties.Schema(properties.Schema.MAP,
                                          schema=rolling_update_schema)
    }

    def handle_create(self):
        return self.create_with_template(self.child_template())

    def _get_members(self, group_id):
        members = []
        for res in self.stack.iter_resources(cfg.CONF.max_nested_stack_depth):
            if (res.type() in ['OS::Nova::Server'] and
                    res.status == res.COMPLETE):
                members.append({
                    'id': res.resource_id,
                    'name': res.name,
                    'group_id': group_id
                })

        return members

    def _add_scheduler(self, group_id):
        task_args = {
            'group_name': 'groupwatch',
            'job_name': group_id,
            'job_type': 'period',
            'trigger_type': 'SIMPLE_TRIGGER',
            'interval': 240,
            'cover_flag': 'true',
            'end_time': 4076884800000,
            'meta_data': {
                'group_id': group_id,
                'project_id': self.context.tenant_id
            }
        }

        rsp = self.client('scheduler').scheduler.create(**task_args)
        return rsp.get('job_id')

    def _create_groupwatch(self):
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        group_id = self.stack.resource_by_refid(self.FnGetRefId()).resource_id
        members = self._get_members(group_id)
        job_id = self._add_scheduler(group_id)
        kwargs = {
            'id': group_id,
            'name': self.name,
            'type': 'VM',
            'data': {'scheduler_job_id': job_id},
            'members': members
        }

        self.client('groupwatch').groups.create(**kwargs)

    def _make_launch_config_resource(self, name, props):
        lc_res_type = 'AWS::AutoScaling::LaunchConfiguration'
        lc_res_def = rsrc_defn.ResourceDefinition(name,
                                                  lc_res_type,
                                                  props)
        lc_res = resource.Resource(name, lc_res_def, self.stack)
        return lc_res

    def _get_conf_properties(self):
        instance_id = self.properties.get(self.INSTANCE_ID)
        if instance_id:
            server = self.client_plugin('nova').get_server(instance_id)
            instance_props = {
                'ImageId': server.image['id'],
                'InstanceType': server.flavor['id'],
                'KeyName': server.key_name,
                'SecurityGroups': [sg['name']
                                   for sg in server.security_groups]
            }
            conf = self._make_launch_config_resource(self.name,
                                                     instance_props)
            props = function.resolve(conf.properties.data)
        else:
            conf, props = super(AutoScalingGroup, self)._get_conf_properties()

        vpc_zone_ids = self.properties.get(self.VPCZONE_IDENTIFIER)
        if vpc_zone_ids:
            props['SubnetId'] = vpc_zone_ids[0]

        return conf, props

    def check_create_complete(self, task):
        """Update cooldown timestamp after create succeeds."""
        done = super(AutoScalingGroup, self).check_create_complete(task)
        if done:
            self._create_groupwatch()
            self._finished_scaling(
                "%s : %s" % (sc_util.CFN_EXACT_CAPACITY,
                             grouputils.get_size(self)))
        return done

    def check_update_complete(self, cookie):
        """Update the cooldown timestamp after update succeeds."""
        done = super(AutoScalingGroup, self).check_update_complete(cookie)
        if done:
            self._finished_scaling(
                "%s : %s" % (sc_util.CFN_EXACT_CAPACITY,
                             grouputils.get_size(self)))
        return done

    def _get_new_capacity(self, capacity,
                          adjustment,
                          adjustment_type=sc_util.CFN_EXACT_CAPACITY,
                          min_adjustment_step=None):
        lower = self.properties[self.MIN_SIZE]
        upper = self.properties[self.MAX_SIZE]
        return sc_util.calculate_new_capacity(capacity, adjustment,
                                              adjustment_type,
                                              min_adjustment_step,
                                              lower, upper)

    def _update_groupwatch(self):
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        group_id = self.stack.resource_by_refid(self.FnGetRefId()).resource_id
        members = self._get_members(group_id)
        kwargs = {
            'id': group_id,
            'name': self.name,
            'type': 'VM',
            'members': members
        }

        self.client('groupwatch').groups.update(group_id, **kwargs)

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        """Updates self.properties, if Properties has changed.

        If Properties has changed, update self.properties, so we get the new
        values during any subsequent adjustment.
        """
        if tmpl_diff:
            # parse update policy
            if 'UpdatePolicy' in tmpl_diff:
                up = json_snippet.update_policy(self.update_policy_schema,
                                                self.context)
                self.update_policy = up

        self.properties = json_snippet.properties(self.properties_schema,
                                                  self.context)
        if prop_diff:
            # Replace instances first if launch configuration has changed
            self._try_rolling_update(prop_diff)

        # Update will happen irrespective of whether auto-scaling
        # is in progress or not.
        capacity = grouputils.get_size(self)
        desired_capacity = self.properties[self.DESIRED_CAPACITY] or capacity
        new_capacity = self._get_new_capacity(capacity, desired_capacity)
        self.resize(new_capacity)

    def adjust(self, adjustment,
               adjustment_type=sc_util.CFN_CHANGE_IN_CAPACITY,
               min_adjustment_step=None):
        """Adjust the size of the scaling group if the cooldown permits."""
        if not self._is_scaling_allowed():
            LOG.info(_LI("%(name)s NOT performing scaling adjustment, "
                         "cooldown %(cooldown)s"),
                     {'name': self.name,
                      'cooldown': self.properties[self.COOLDOWN]})
            raise exception.NoActionRequired()

        capacity = grouputils.get_size(self)
        new_capacity = self._get_new_capacity(capacity, adjustment,
                                              adjustment_type,
                                              min_adjustment_step)

        changed_size = new_capacity != capacity
        # send a notification before, on-error and on-success.
        notif = {
            'stack': self.stack,
            'adjustment': adjustment,
            'adjustment_type': adjustment_type,
            'capacity': capacity,
            'groupname': self.FnGetRefId(),
            'message': _("Start resizing the group %(group)s") % {
                'group': self.FnGetRefId()},
            'suffix': 'start',
        }
        notification.send(**notif)
        try:
            self.resize(new_capacity)
        except Exception as resize_ex:
            with excutils.save_and_reraise_exception():
                try:
                    notif.update({'suffix': 'error',
                                  'message': six.text_type(resize_ex),
                                  'capacity': grouputils.get_size(self),
                                  })
                    notification.send(**notif)
                except Exception:
                    LOG.exception(_LE('Failed sending error notification'))
        else:
            notif.update({
                'suffix': 'end',
                'capacity': new_capacity,
                'message': _("End resizing the group %(group)s") % {
                    'group': notif['groupname']},
            })
            notification.send(**notif)
        finally:
            self._update_groupwatch()
            self._finished_scaling("%s : %s" % (adjustment_type, adjustment),
                                   changed_size=changed_size)
        return changed_size

    def _tags(self):
        """Add Identifying Tags to all servers in the group.

        This is so the Dimensions received from cfn-push-stats all include
        the groupname and stack id.
        Note: the group name must match what is returned from FnGetRefId
        """
        autoscaling_tag = [{self.TAG_KEY: 'metering.AutoScalingGroupName',
                            self.TAG_VALUE: self.FnGetRefId()}]
        return super(AutoScalingGroup, self)._tags() + autoscaling_tag

    def validate(self):
        # check validity of group size
        min_size = self.properties[self.MIN_SIZE]
        max_size = self.properties[self.MAX_SIZE]

        if max_size < min_size:
            msg = _("MinSize can not be greater than MaxSize")
            raise exception.StackValidationFailed(message=msg)

        if min_size < 0:
            msg = _("The size of AutoScalingGroup can not be less than zero")
            raise exception.StackValidationFailed(message=msg)

        if self.properties[self.DESIRED_CAPACITY] is not None:
            desired_capacity = self.properties[self.DESIRED_CAPACITY]
            if desired_capacity < min_size or desired_capacity > max_size:
                msg = _("DesiredCapacity must be between MinSize and MaxSize")
                raise exception.StackValidationFailed(message=msg)

        # TODO(pasquier-s): once Neutron is able to assign subnets to
        # availability zones, it will be possible to specify multiple subnets.
        # For now, only one subnet can be specified. The bug #1096017 tracks
        # this issue.
        if (self.properties.get(self.VPCZONE_IDENTIFIER) and
                len(self.properties[self.VPCZONE_IDENTIFIER]) != 1):
            raise exception.NotSupported(feature=_("Anything other than one "
                                         "VPCZoneIdentifier"))
        # validate properties InstanceId and LaunchConfigurationName
        # for aws auto scaling group.
        # should provide just only one of
        if self.type() == 'AWS::AutoScaling::AutoScalingGroup':
            instanceId = self.properties.get(self.INSTANCE_ID)
            launch_config = self.properties.get(
                self.LAUNCH_CONFIGURATION_NAME)
            if bool(instanceId) == bool(launch_config):
                msg = _("Either 'InstanceId' or 'LaunchConfigurationName' "
                        "must be provided.")
                raise exception.StackValidationFailed(message=msg)

        super(AutoScalingGroup, self).validate()

    def _resolve_attribute(self, name):
        """Resolves the resource's attributes.

        heat extension: "InstanceList" returns comma delimited list of server
        ip addresses.
        """
        if name == self.INSTANCE_LIST:
            return u','.join(inst.FnGetAtt('PublicIp')
                             for inst in grouputils.get_members(self)) or None

    def child_template(self):
        if self.properties[self.DESIRED_CAPACITY]:
            num_instances = self.properties[self.DESIRED_CAPACITY]
        else:
            num_instances = self.properties[self.MIN_SIZE]
        return self._create_template(num_instances)

    def _delete_groupwatch(self):
        if not cfg.CONF.FusionSphere.groupwatch_enable:
            return

        if not self.resource_id:
            return

        group = None
        try:
            group = self.client('groupwatch').groups.get(self.resource_id)
        except Exception as ex:
            self.client_plugin('groupwatch').ignore_not_found(ex)
            return

        try:
            if (group and group.get('group') and
                    'data' in group.get('group')):
                scheduler_job_id = \
                    group.get('group').get('data').get('scheduler_job_id')
                self.client('scheduler').scheduler.delete(scheduler_job_id)
        except (AttributeError, KeyError):
            # do nothing
            pass
        except Exception as ex:
            self.client_plugin('scheduler').ignore_not_found(ex)

        try:
            self.client('groupwatch').groups.delete(self.resource_id)
        except Exception as ex:
            self.client_plugin('groupwatch').ignore_not_found(ex)

    def handle_delete(self):
        self._delete_groupwatch()
        return self.delete_nested()

    def handle_metadata_reset(self):
        metadata = self.metadata_get()
        if 'scaling_in_progress' in metadata:
            metadata['scaling_in_progress'] = False
            self.metadata_set(metadata)


def resource_mapping():
    return {
        'AWS::AutoScaling::AutoScalingGroup': AutoScalingGroup,
    }
