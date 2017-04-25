# Copyright (c) 2014, Huawei Technologies Co., Ltd
# All rights reserved.

import json
import six
import time
import traceback

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import threadgroup
from oslo_utils import importutils
from oslo_utils import timeutils

from novaclient import client as novaclient

from conveyor.conveyorheat.common import config
from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.db import api as db_api
from conveyor.conveyorheat.engine import attributes
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import event
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.cps_httputils import CpsHTTPClient
from conveyor.conveyorheat.engine.resources import signal_responder
from conveyor.conveyorheat.engine import scheduler
from conveyor.conveyorheat.engine import support
from conveyor.conveyorheat.objects import resource as resource_objects

LOG = logging.getLogger(__name__)

BUILDING = 'building'
STOPPED = 'stopped'

CHECK_INTERVAL = 5
CPS_CONNECTION_TIMEOUT = 30

ha_opts = [
    cfg.BoolOpt('ha_policy_enable',
                default=False,
                help='Enable ha policy to handle error VMs'),
    cfg.StrOpt('ha_timeout',
               default=300,
               help='Timeout of wait for HA')
]

cfg.CONF.register_opts(ha_opts)


class TimeStampConflictError(Exception):
    pass


class HAPolicy(signal_responder.SignalResponder):

    PROPERTIES = (
        METER_TYPE, REPEAT_ACTION,
    ) = (
        'MeterType', 'RepeatAction',
    )

    INSTANCE, HOST = (
        'instance', 'host')

    ATTRIBUTES = (
        ALARM_URL,
    ) = (
        'AlarmUrl',
    )

    properties_schema = {
        METER_TYPE: properties.Schema(
            properties.Schema.STRING,
            _('AutoScaling group name to apply policy to.'),
            constraints=[
                constraints.AllowedValues([INSTANCE,
                                           HOST]),
            ],
            required=True
        ),
        REPEAT_ACTION: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Not Implemented.'),
            default=True,
            support_status=support.SupportStatus(
                support.DEPRECATED,
                _('Please use ceilometer alarm repeat action')
            )
        )
    }

    attributes_schema = {
        ALARM_URL: attributes.Schema(
            _("A signed url to handle the alarm (Heat extension)."),
            type=attributes.Schema.STRING
        ),
    }

    def __init__(self, name, json_snippet, stack):
        super(HAPolicy, self).__init__(name, json_snippet, stack)
        self._admin_nova_client = None
        self._user_nova_client = None

    def handle_create(self):
        super(HAPolicy, self).handle_create()
        self.resource_id_set(self._get_user_id())

    def check_instance_deleted(self, inst_id):
        try:
            servers = self._admin_novaclient().\
                servers.list(search_opts={"uuid": inst_id, "deleted": True})
            if len(servers):
                return True
        except Exception:
            LOG.error('Get the servers fail, exception: %s' %
                      (traceback.format_exc()))

        return False

    @resource_objects.retry_on_conflict
    def metadata_set(self, metadata, merge_metadata=None):
        """Write new metadata to the database.

        The caller may optionally provide a merge_metadata() function, which
        takes two arguments - the metadata passed to metadata_set() and the
        current metadata of the resource - and returns the merged metadata to
        write. If merge_metadata is not provided, the metadata passed to
        metadata_set() is written verbatim, overwriting any existing metadata.

        If a race condition is detected, the write will be retried with the new
        result of merge_metadata() (if it is supplied) or the verbatim data (if
        it is not).
        """
        if self.id is None or self.action == self.INIT:
            raise exception.ResourceNotAvailable(resource_name=self.name)
        LOG.debug('Setting metadata for %s', six.text_type(self))
        from conveyor.conveyorheat.common import context as ctx
        context = ctx.RequestContext()
        context._session = db_api.get_session()
        db_res = resource_objects.Resource.get_obj(context, self.id)
        if merge_metadata is not None:
            db_res = db_res.refresh(attrs=['rsrc_metadata'])
            metadata = merge_metadata(metadata, db_res.rsrc_metadata)
        db_res.update_metadata(metadata)
        self._rsrc_metadata = metadata

    def _add_event(self, action, status, reason):
        """Add a state change event to the database."""
        from conveyor.conveyorheat.common import context as ctx
        context = ctx.RequestContext()
        context._session = db_api.get_session()
        ev = event.Event(context, self.stack, action, status, reason,
                         self.resource_id, self.properties,
                         self.name, self.type())

        ev.store()
        self.stack.dispatch_event(ev)

    def _wait(self, **kwargs):
        resource_id = kwargs.get('resource_id')
        host_id = kwargs.get('host_id')
        alarm_type = kwargs.get('alarm_type')
        tmstamp_ex = kwargs["tmstamp"]
        LOG.info('The task is running, resource: %s, alarm_type: %s' %
                 (resource_id, alarm_type))
        while True:
            try:
                yield
            except scheduler.Timeout:
                LOG.info('%s Timed out, resource_id: %s' %
                         (str(self), resource_id))

                try:
                    if alarm_type == self.HOST and \
                            not self.check_host_state(host_id):

                        LOG.info("Check host state failed, don't rescheduler,"
                                 " host_id: %s" % host_id)
                        return

                    server = self._admin_novaclient().servers.get(resource_id)

                    if not self.check_instance_state(alarm_type, server):
                        LOG.info("Check state fail, don't rescheduler, "
                                 "server: %s" % server.id)
                        return

                    self._admin_novaclient().servers._action(
                        "reschedule",
                        server
                    )
                except Exception as ex:
                    LOG.error("Action the scheduler timeout failed, "
                              "exception: %s" % str(ex))

            # don't query metadata too frequently
            time.sleep(CHECK_INTERVAL)
            rsc_metadata = self._get_metadata()
            task_list = rsc_metadata.get('task_list', {})
            if resource_id not in task_list.keys():
                LOG.info('The task has been end, resource: %s' % resource_id)
                return
            else:
                tmstamp = task_list.get(resource_id)
                if tmstamp_ex != tmstamp:
                    LOG.debug("timestamp is conflict, id: %s tmstamp_ex %s "
                              "tmstamp %s" %
                              (resource_id, tmstamp_ex, tmstamp))
                    raise TimeStampConflictError('timestamp is conflict')

    def _get_resource_id(self, details):
        # Get resource_id from alarm name
        try:
            resource_id = eval(details['reason'])['resource_id']
            return resource_id
        except Exception as ex:
            LOG.error('Get the resource_id fail, exception: %s' % str(ex))
            return None

    def _check_server_force(self, server):
        metadata = getattr(server, 'metadata', {})
        force_host = metadata.get('force_host', None)
        if force_host:
            return True
        return False

    def _check_HA_available(self, server):
        metadata = getattr(server, 'metadata', {})
        HA_available = metadata.get('_ha_policy_type', 'remote_rebuild')
        if 'remote_rebuild' != HA_available:
            return False
        return True

    def _get_instance_list(self, resource_id, alarm_type):
        tmp_list = []
        if self.INSTANCE == alarm_type:
            tmp_list.append(resource_id)
            LOG.info('the %s tmp_list is %s' % (alarm_type, tmp_list))
        else:
            try:
                con = self.stack.clients.context
                servers = self._admin_novaclient().servers.list(
                    search_opts={
                        "host": resource_id,
                        "all_tenants": True,
                        "tenant_id": con.tenant_id
                    }
                )
            except Exception as e:
                LOG.error("Get the server failed, check if the server is "
                          "exist, id: %s %s" % (resource_id, e))
                return tmp_list
            for server in servers:
                tmp_server = server.__dict__
                tmp_list.append(tmp_server['id'])
            LOG.info('the %s tmp_list is %s' % (alarm_type, tmp_list))
        return tmp_list

    def _check_available_and_time(self, server,
                                  pre_time=None, alarm_type=None):
        check_force = self._check_server_force(server)
        check_available = self._check_HA_available(server)

        if check_force or not check_available:
            LOG.info("The reason of not remote rebuild : force_host %s, "
                     "ha_policy_type %s" % (check_force, check_available))
            return False

        if pre_time:
            metadata = getattr(server, 'metadata', {})
            tmp_timeout = metadata.get('_ha_policy_time', cfg.CONF.ha_timeout)
            if not tmp_timeout.isdigit():
                timeout = cfg.CONF.ha_timeout
            else:
                timeout = int(tmp_timeout)

            cooldown = timeout + CHECK_INTERVAL * 4
            is_older = timeutils.is_older_than(pre_time, cooldown)
            is_newer = timeutils.is_newer_than(pre_time, 0)
            if not is_older and not is_newer:
                LOG.info("instance %s is in task, pre_time %s timeout %s" %
                         (server.id, pre_time, tmp_timeout))
                return False

        return self.check_instance_state(alarm_type, server)

    def check_host_state(self, host_id):
        # If alarm type is host, before reschedule VMs on this host we must
        # judge whether HOST is normal now. If status is nomal, no need to
        # reschedule VMs, return False, else return True
        if not host_id:
            return True
        LOG.debug('check host state, host_id: %s' % host_id)
        insecure = config.get_client_option('cps', 'insecure')
        if insecure:
            verify = False
        else:
            verify = config.get_client_option('cps', 'ca_file') or True

        code, state_str = CpsHTTPClient.rest_cps_execute(
            'GET',
            '/cps/v1/hosts/%s/hoststate' % host_id,
            time=CPS_CONNECTION_TIMEOUT,
            verify=verify)

        if code != 200:
            LOG.warning('get host status error, code: %s' % code)
            return False

        state_json = None
        try:
            state_json = json.loads(state_str)
        except Exception:
            LOG.error('get host status error, state: %s' % state_str)
            return False

        if 'state' in state_json and state_json['state'] == 'normal':
            LOG.debug('check host state, host %s is normal.' % host_id)
            return False

        return True

    # check instance state
    def check_instance_state(self, alarm_type, server):
        vm_state = getattr(server, 'OS-EXT-STS:vm_state').lower()
        power_state = getattr(server, 'OS-EXT-STS:power_state')
        LOG.debug("check instance state, instance:%s v_state:%s p_state:%s" %
                  (server.id, vm_state, power_state))
        state = power_state
        if "error" == vm_state:
            state = 0x10
        elif vm_state in ("building", "stopped"):
            state = 0x00
        elif "paused" == vm_state and 0x03 == power_state:
            state = 0x00
        elif "suspended" == vm_state and 0x04 == power_state:
            state = 0x00
        elif "active" == vm_state and 0x03 == power_state:
            state = 0x00
        is_error = (state > 0x01)
        LOG.debug("instance state is instance:%s error:%s" %
                  (server.id, is_error))

        if alarm_type:
            if alarm_type == self.INSTANCE and is_error:
                return True
            elif alarm_type == self.HOST and not is_error:
                return True
            else:
                return False
        else:
            return True

    def _remove_instance_id(self, instance_id):
        for i in xrange(10):
            try:
                rsc_metadata = self._get_metadata()
                LOG.debug('Currect metadata is: %s!' % rsc_metadata)
                task_list = rsc_metadata.get('task_list', {})
                if instance_id in task_list.keys():
                    LOG.info('Remove resource task: %s!' % instance_id)
                    del task_list[instance_id]
                    rsc_metadata.update({'task_list': task_list})
                    self._set_metadata(rsc_metadata)
                return
            except Exception as ex:
                LOG.info('update metadata fail, ex: %s, retry' % str(ex))
                time.sleep(1)

        # throw an exception if it still fails after several retries
        raise exception.Error(_('Cannot remove instance: %s') % self.name)

    def _add_instance_id(self, instance_id, tmp_timeout):
        timeout = int(tmp_timeout)
        for i in xrange(10):
            try:
                rsc_metadata = self._get_metadata()
                LOG.debug('Currect metadata is: %s!' % rsc_metadata)
                task_list = rsc_metadata.get('task_list', {})
                if instance_id in task_list:
                    pre_time = task_list[instance_id]
                    cooldown = timeout + CHECK_INTERVAL * 4
                    is_older = timeutils.is_older_than(pre_time, cooldown)
                    is_newer = timeutils.is_newer_than(pre_time, 0)
                    if not is_older and not is_newer:
                        LOG.info("instance %s is in task, pre_time %s "
                                 "timeout %s" %
                                 (instance_id, pre_time, tmp_timeout))
                        msg = _('Cannot remove instance: %s') % self.name
                        raise exception.Error(msg)

                task_list[instance_id] = timeutils.strtime()
                LOG.info('add resource task: %s, timestamp:%s' %
                         (instance_id, task_list[instance_id]))
                rsc_metadata.update({'task_list': task_list})
                self._set_metadata(rsc_metadata)
                return task_list[instance_id]
            except Exception as ex:
                LOG.info('update metadata fail, ex: %s, retry' % str(ex))
                time.sleep(1)

        # throw an exception if it still fails after several retries
        raise exception.Error(_('Cannot remove instance for %s') %
                              self.name)

    def handle_signal(self, details=None):
        """Handle ceilometer alarm signal.

        ceilometer sends details like this:
        {u'alarm_id': ID, u'previous': u'ok', u'current': u'alarm',
        u'reason': u'...'})
        in this policy we currently assume that this gets called
        only when there is an alarm. But the template writer can
        put the policy in all the alarm notifiers (nodata, and ok).
        our watchrule has upper case states so lower() them all.
        """
        if not cfg.CONF.ha_policy_enable:
            LOG.info("HA is disabled, return")
            raise exception.Error('HA is disabled')

        if details is None:
            alarm_state = 'alarm'
        else:
            alarm_state = details.get('current',
                                      details.get('state', 'alarm')).lower()

        LOG.info('%s Alarm, new state %s, details: %s' %
                 (self.name, alarm_state, details))

        resource_id = self._get_resource_id(details)
        if resource_id is None or len(resource_id) == 0:
            LOG.error('The resource_id is None, details: %s' % details)
            return
        alarm_type = self.properties[self.METER_TYPE]
        if alarm_type is None or len(alarm_type) == 0:
            LOG.error('The type is None, details: %s' % details)
            return

        instance_list = self._get_instance_list(resource_id, alarm_type)

        host_id = resource_id if alarm_type == self.HOST else ''
        self.update_metadata(instance_list, host_id, alarm_state, alarm_type)
        LOG.info('Handle signal end!')

    def monitor_thread(self, **kwargs):
        alarm_type = kwargs["alarm_type"]
        resource_id = kwargs["resource_id"]
        host_id = kwargs["host_id"]
        try:
            if alarm_type == self.HOST and not self.check_host_state(host_id):
                LOG.info("Check host state failed, don't rescheduler,"
                         " host_id: %s" % host_id)
                self._remove_instance_id(resource_id)
                return

            try:
                server = self._admin_novaclient().servers.get(resource_id)
            except Exception as ex:
                LOG.error("Get the server failed, check if the server is "
                          "exist, id: %s, kwargs: %s" %
                          (resource_id, str(ex)))
                self._remove_instance_id(resource_id)
                return

            if not self.check_instance_state(alarm_type, server):
                LOG.info("Check state fail, don't rescheduler, "
                         "server: %s" % server.id)
                self._remove_instance_id(resource_id)
                return

            if getattr(server, 'OS-EXT-STS:vm_state', None) == STOPPED:
                LOG.info("The vm is stopped, don't rescheduler, server: %s"
                         % server.id)
                self._remove_instance_id(resource_id)
                return

            metadata = getattr(server, 'metadata', {})
            tmp_timeout = metadata.get('_ha_policy_time', cfg.CONF.ha_timeout)
            if not tmp_timeout.isdigit():
                timeout = cfg.CONF.ha_timeout
            else:
                timeout = int(tmp_timeout)

            runner = scheduler.TaskRunner(self._wait, **kwargs)
            runner(timeout=timeout)

            self._remove_instance_id(resource_id)
            LOG.info('End the task runner, timeout: %s, kwargs: %s' %
                     (timeout, kwargs))
        except TimeStampConflictError:
            LOG.error('timestamp conflict, ha exit')
        except Exception as ex:
            LOG.error('monitor fail, exception: %s' %
                      (traceback.format_exc()))
            self._remove_instance_id(resource_id)

    def update_metadata(self, instance_list, host_id, alarm_state, alarm_type):
        rsc_metadata = self._get_metadata()
        LOG.debug('Currect metadata is: %s!' % rsc_metadata)
        task_list = rsc_metadata.get('task_list', {})
        if alarm_state != 'ok':
            # if resource_id not in task_list:
            # Start an task and update the metadata
            task_map = threadgroup.ThreadGroup(thread_pool_size=75)

            # save HA running flag
            ha_running = False
            for instance_id in instance_list:
                try:
                    server = self._admin_novaclient().servers.\
                        get(instance_id)
                except Exception as ex:
                    LOG.error("Get the server failed, check if the "
                              "server is exist, trac_back: %s" %
                              str(ex))
                    continue

                metadata = getattr(server, 'metadata', {})
                tmp_timeout = metadata.get('_ha_policy_time',
                                           cfg.CONF.ha_timeout)
                available = self._check_available_and_time(
                    server, alarm_type=alarm_type)
                if instance_id not in task_list.keys() and available:
                    tmstamp = self._add_instance_id(instance_id,
                                                    tmp_timeout)
                    task_map.add_thread(self.monitor_thread,
                                        resource_id=instance_id,
                                        host_id=host_id,
                                        alarm_type=alarm_type,
                                        tmstamp=tmstamp)
                    ha_running = False
                elif instance_id in task_list.keys():
                    pre_time = task_list[instance_id]
                    if self._check_available_and_time(server, pre_time,
                                                      alarm_type=alarm_type):
                        tmstamp = self._add_instance_id(instance_id,
                                                        tmp_timeout)
                        task_map.add_thread(self.monitor_thread,
                                            resource_id=instance_id,
                                            host_id=host_id,
                                            alarm_type=alarm_type,
                                            tmstamp=tmstamp)
                        ha_running = False
                    else:
                        ha_running = True

                if ha_running:
                    LOG.warning('HA-%s-%s is running.' % (
                        instance_id, alarm_type))
        else:
            for instance_id in instance_list:
                self._remove_instance_id(instance_id)

    def _set_metadata(self, metadata):
        for i in xrange(10):
            try:
                self.metadata_set(metadata)
                return
            except Exception as ex:
                LOG.info('update metadata fail, ex: %s, retry' % str(ex))
                time.sleep(1)

        # throw an exception if it still fails after several retries
        raise exception.Error(_('Cannot set metadata for %s') % self.name)

    def _get_metadata(self):
        for i in xrange(10):
            try:
                rs = self.metadata_get(refresh=True)
                return rs
            except Exception as ex:
                LOG.info('get metadata fail, ex: %s, retry' % str(ex))
                time.sleep(1)

        # throw an exception if it still fails after several retries
        raise exception.Error(_('Cannot get metadata from %s') % self.name)

    def _nova_client(self, username=None,
                     password=None, project_id=None, token=None):

        extensions = novaclient.discover_extensions("1.1")
        endpoint_type = 'internalURL'
        region_name = cfg.CONF.region_name_for_services
        clients = self.stack.clients
        args = {
            'project_id': project_id,
            'auth_url': cfg.CONF.keystone_authtoken.auth_uri,
            'service_type': 'compute',
            'username': username,
            'api_key': password,
            'extensions': extensions,
            'region_name': region_name,
            'endpoint_type': endpoint_type,
            'insecure': config.get_client_option('nova', 'insecure'),
            'cacert': config.get_client_option('nova', 'ca_file'),
            'timeout': 30
        }

        client = novaclient.Client(1.1, **args)

        if token:
            management_url = clients.url_for(service_type='compute',
                                             filter_value=region_name,
                                             attr='region',
                                             endpoint_type=endpoint_type)
            client.client.auth_token = self.stack.clients.auth_token
            client.client.management_url = management_url

        return client

    def _admin_novaclient(self):
        if self._admin_nova_client:
            return self._admin_nova_client

        importutils.import_module('keystonemiddleware.auth_token')
        self._admin_nova_client = self._nova_client(
            username=cfg.CONF.keystone_authtoken.admin_user,
            password=cfg.CONF.keystone_authtoken.admin_password,
            project_id='service'
        )
        return self._admin_nova_client

    def _resolve_attribute(self, name):
        '''Get policy signal url

        heat extension: "AlarmUrl" returns the url to post to the policy
        when there is an alarm.
        '''
        if name == self.ALARM_URL and self.resource_id is not None:
            return unicode(self._get_ec2_signed_url())

    def FnGetRefId(self):
        if self.resource_id is not None:
            return unicode(self._get_ec2_signed_url())
        else:
            return unicode(self.name)

    @property
    def stack(self):
        stack = self._stackref
        assert stack is not None, "Need a reference to the Stack object"
        return stack

    @stack.setter
    def stack(self, stack):
        self._stackref = stack


def resource_mapping():
    return {
        'Huawei::FusionSphere::HAPolicy': HAPolicy,
    }
