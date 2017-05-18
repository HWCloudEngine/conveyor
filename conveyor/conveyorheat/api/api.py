# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import contextlib
import functools
from oslo_config import cfg
from oslo_utils import timeutils
import six
import itertools

from conveyor.conveyorheat.common import template_format
from conveyor.conveyorheat.common import urlfetch
from conveyor.conveyorheat.common import environment_format
from conveyor.conveyorheat.common import param_utils
from conveyor.conveyorheat.common import identifier
from conveyor.conveyorheat.engine import service as engine
from conveyor.conveyorheat.hw_plugins import utils
from conveyor.conveyorheat.rpc import api as rpc_api

from conveyor.common._i18n import _
from conveyor.common import loopingcall
from webob import exc

from conveyor import exception
from oslo_log import log as logging

from conveyor.db import api as db_api

LOG = logging.getLogger(__name__)

heat_opts = [
    cfg.StrOpt('heat_url',
               default='https://127.0.0.1:8700/v1',
               help='Default heat URL',
               deprecated_group='DEFAULT',
               deprecated_name='heat_url')
    ]

CONF = cfg.CONF

CONF.register_opts(heat_opts, 'heat')
# Mapping of V2 Catalog Endpoint_type to V3 Catalog Interfaces
ENDPOINT_TYPE_TO_INTERFACE = {
    'publicURL': 'public',
    'internalURL': 'internal',
    'adminURL': 'admin',
}


def get_service_from_catalog(catalog, service_type):
    if catalog:
        for service in catalog:
            if 'type' not in service:
                continue
            if service['type'] == service_type:
                return service
    return None


def get_version_from_service(service):
    if service and service.get('endpoints'):
        endpoint = service['endpoints'][0]
        if 'interface' in endpoint:
            return 3
        else:
            return 2.0
    return 2.0


def _get_endpoint_region(endpoint):
    """Common function for getting the region from endpoint.

    In Keystone V3, region has been deprecated in favor of
    region_id.

    This method provides a way to get region that works for
    both Keystone V2 and V3.
    """
    return endpoint.get('region_id') or endpoint.get('region')


def get_url_for_service(service, endpoint_type, region=None):
    if 'type' not in service:
        return None

    identity_version = get_version_from_service(service)
    service_endpoints = service.get('endpoints', [])
    if region:
        available_endpoints = [endpoint for endpoint in service_endpoints
                               if region == _get_endpoint_region(endpoint)]
    else:
        available_endpoints = service_endpoints
    """if we are dealing with the identity service and there is no endpoint
    in the current region, it is okay to use the first endpoint for any
    identity service endpoints and we can assume that it is global
    """
    if service['type'] == 'identity' and not available_endpoints:
        available_endpoints = [endpoint for endpoint in service_endpoints]

    for endpoint in available_endpoints:
        try:
            if identity_version < 3:
                return endpoint.get(endpoint_type)
            else:
                interface = \
                    ENDPOINT_TYPE_TO_INTERFACE.get(endpoint_type, '')
                if endpoint.get('interface') == interface:
                    return endpoint.get('url')
        except (IndexError, KeyError):
            """it could be that the current endpoint just doesn't match the
            type, continue trying the next one
            """
            pass
    return None


def url_for(context, service_type, endpoint_type=None, region=None):
    endpoint_type = endpoint_type or getattr(CONF,
                                             'OPENSTACK_ENDPOINT_TYPE',
                                             'publicURL')
    fallback_endpoint_type = getattr(CONF, 'SECONDARY_ENDPOINT_TYPE', None)
    region = getattr(CONF, 'os_region_name', None)

    catalog = context.service_catalog
    service = get_service_from_catalog(catalog, service_type)
    if service:
        url = get_url_for_service(service,
                                  endpoint_type,
                                  region=region)
        if not url and fallback_endpoint_type:
            url = get_url_for_service(service,
                                      fallback_endpoint_type,
                                      region=region)
        if url:
            return url
    raise exception.ServiceCatalogException(service_type)


def make_url(req, identity):
    """Return the URL for the supplied identity dictionary."""
    try:
        stack_identity = identifier.HeatIdentifier(**identity)
    except ValueError:
        err_reason = _('Invalid Stack address')
        raise exc.HTTPInternalServerError(err_reason)

    if cfg.CONF.FusionSphere.pubcloud:
        url = cfg.CONF.FusionSphere.heat_orchestration_url
        if url:
            return '%s/%s' % (url.rstrip('/'), stack_identity.url_path())

    return req.relative_url(stack_identity.url_path(), True)


def format_stack(stack, keys=None, tenant_safe=True):
    def transform(key, value):
        if keys and key not in keys:
            return

        if key == rpc_api.STACK_ID:
            yield ('id', value['stack_id'])
            #yield ('links', [make_link(req, value)])
            if not tenant_safe:
                yield ('project', value['tenant'])
        elif key == rpc_api.STACK_ACTION:
            return
        elif (key == rpc_api.STACK_STATUS and
              rpc_api.STACK_ACTION in stack):
            # To avoid breaking API compatibility, we join RES_ACTION
            # and RES_STATUS, so the API format doesn't expose the
            # internal split of state into action/status
            yield (key, '_'.join((stack[rpc_api.STACK_ACTION], value)))
        else:
            # TODO(zaneb): ensure parameters can be formatted for XML
            # elif key == rpc_api.STACK_PARAMETERS:
            #     return key, json.dumps(value)
            yield (key, value)

    return dict(itertools.chain.from_iterable(
        transform(k, v) for k, v in stack.items()))


def format_resource(res, keys=None):
    keys = keys or []

    def include_key(k):
        return k in keys if keys else True

    def transform(key, value):
        if not include_key(key):
            return

        if key == rpc_api.RES_ID:
            identity = identifier.ResourceIdentifier(**value)
            # links = [util.make_link(req, identity),
            #          util.make_link(req, identity.stack(), 'stack')]

            # nested_id = res.get(rpc_api.RES_NESTED_STACK_ID)
            # if nested_id:
            #     nested_identity = identifier.HeatIdentifier(**nested_id)
            #     links.append(util.make_link(req, nested_identity, 'nested'))
            #
            # yield ('links', links)
        elif (key == rpc_api.RES_STACK_NAME or
              key == rpc_api.RES_STACK_ID or
              key == rpc_api.RES_ACTION or
              key == rpc_api.RES_NESTED_STACK_ID):
            return
        elif key == rpc_api.RES_METADATA:
            return
        elif key == rpc_api.RES_STATUS and rpc_api.RES_ACTION in res:
            # To avoid breaking API compatibility, we join RES_ACTION
            # and RES_STATUS, so the API format doesn't expose the
            # internal split of state into action/status
            yield (key, '_'.join((res[rpc_api.RES_ACTION], value)))
        elif key == rpc_api.RES_NAME:
            yield ('logical_resource_id', value)
            yield (key, value)

        else:
            yield (key, value)

    return dict(itertools.chain.from_iterable(
        transform(k, v) for k, v in res.items()))


def format_event(event, keys=None):

    def include_key(k):
        return k in keys if keys else True

    def transform(key, value):
        if not include_key(key):
            return

        if key == rpc_api.EVENT_ID:
            identity = identifier.EventIdentifier(**value)
            yield ('id', identity.event_id)
            # yield ('links', [util.make_link(req, identity),
            #                  util.make_link(req, identity.resource(),
            #                                 'resource'),
            #                  util.make_link(req, identity.stack(),
            #                                 'stack')])
        elif key in (rpc_api.EVENT_STACK_ID, rpc_api.EVENT_STACK_NAME,
                     rpc_api.EVENT_RES_ACTION):
            return
        elif (key == rpc_api.EVENT_RES_STATUS and
              rpc_api.EVENT_RES_ACTION in event):
            # To avoid breaking API compatibility, we join RES_ACTION
            # and RES_STATUS, so the API format doesn't expose the
            # internal split of state into action/status
            yield (key, '_'.join((event[rpc_api.EVENT_RES_ACTION], value)))
        elif key == rpc_api.RES_NAME:
            yield ('logical_resource_id', value)
            yield (key, value)

        else:
            yield (key, value)

    return dict(itertools.chain.from_iterable(
        transform(k, v) for k, v in event.items()))


class InstantiationData(object):
    """The data to create or update a stack.

    The data accompanying a PUT or POST request.
    """

    PARAMS = (
        PARAM_STACK_NAME,
        PARAM_TEMPLATE,
        PARAM_TEMPLATE_URL,
        PARAM_USER_PARAMS,
        PARAM_ENVIRONMENT,
        PARAM_FILES,
        PARAM_ENVIRONMENT_FILES,
    ) = (
        'stack_name',
        'template',
        'template_url',
        'parameters',
        'environment',
        'files',
        'environment_files',
    )

    def __init__(self, data, patch=False):
        """Initialise from the request object.

        If called from the PATCH api, insert a flag for the engine code
        to distinguish.
        """
        self.data = data
        self.patch = patch
        if patch:
            self.data[rpc_api.PARAM_EXISTING] = True

    @staticmethod
    @contextlib.contextmanager
    def parse_error_check(data_type):
        try:
            yield
        except ValueError as parse_ex:
            mdict = {'type': data_type, 'error': six.text_type(parse_ex)}
            msg = _("%(type)s not in valid format: %(error)s") % mdict
            raise exc.HTTPBadRequest(msg)

    def stack_name(self):
        """Return the stack name."""
        if self.PARAM_STACK_NAME not in self.data:
            raise exc.HTTPBadRequest(_("No stack name specified"))
        return self.data[self.PARAM_STACK_NAME]

    def template(self):
        """Get template file contents.

        Get template file contents, either inline, from stack adopt data or
        from a URL, in JSON or YAML format.
        """
        template_data = None
        if rpc_api.PARAM_ADOPT_STACK_DATA in self.data:
            adopt_data = self.data[rpc_api.PARAM_ADOPT_STACK_DATA]
            try:
                adopt_data = template_format.simple_parse(adopt_data)
                template_format.validate_template_limit(
                    six.text_type(adopt_data['template']))
                return adopt_data['template']
            except (ValueError, KeyError) as ex:
                err_reason = _('Invalid adopt data: %s') % ex
                raise exc.HTTPBadRequest(err_reason)
        elif self.PARAM_TEMPLATE in self.data:
            template_data = self.data[self.PARAM_TEMPLATE]
            if isinstance(template_data, dict):
                template_format.validate_template_limit(six.text_type(
                    template_data))
                return template_data

        elif self.PARAM_TEMPLATE_URL in self.data:
            url = self.data[self.PARAM_TEMPLATE_URL]
            LOG.debug('TemplateUrl %s' % url)
            try:
                template_data = urlfetch.get(url)
            except IOError as ex:
                err_reason = _('Could not retrieve template: %s') % ex
                raise exc.HTTPBadRequest(err_reason)

        if template_data is None:
            if self.patch:
                return None
            else:
                raise exc.HTTPBadRequest(_("No template specified"))

        with self.parse_error_check('Template'):
            return template_format.parse(template_data)

    def environment(self):
        """Get the user-supplied environment for the stack in YAML format.

        If the user supplied Parameters then merge these into the
        environment global options.
        """
        env = {}
        if self.PARAM_ENVIRONMENT in self.data:
            env_data = self.data[self.PARAM_ENVIRONMENT]
            if isinstance(env_data, dict):
                env = env_data
            else:
                with self.parse_error_check('Environment'):
                    env = environment_format.parse(env_data)

        environment_format.default_for_missing(env)
        parameters = self.data.get(self.PARAM_USER_PARAMS, {})
        env[self.PARAM_USER_PARAMS].update(parameters)
        return env

    def files(self):
        return self.data.get(self.PARAM_FILES, {})

    def environment_files(self):
        return self.data.get(self.PARAM_ENVIRONMENT_FILES, None)

    def args(self):
        """Get any additional arguments supplied by the user."""
        params = self.data.items()
        return dict((k, v) for k, v in params if k not in self.PARAMS)


class base(object):
    def __init__(self, info, loaded=True):
        """Populate and bind to a manager.

        :param info: dictionary representing resource attributes
        :param loaded: prevent lazy-loading if set to True
        """
        self._info = info
        self._add_details(info)
        self._loaded = loaded

    def _add_details(self, info):
        for (k, v) in six.iteritems(info):
            try:
                setattr(self, k, v)
                self._info[k] = v
            except AttributeError:
                # In this case we already defined the attribute on the class
                pass

    def __getattr__(self, k):
        return self.__dict__[k]


class Stack(base):
    @property
    def action(self):
        s = self.stack_status
        # Return everything before the first underscore
        return s[:s.index('_')]

    @property
    def status(self):
        s = self.stack_status
        # Return everything after the first underscore
        return s[s.index('_') + 1:]

    @property
    def identifier(self):
        return '%s/%s' % (self.stack_name, self.id)


class Event(base):
    def __repr__(self):
        return "<Event %s>" % self._info


class Resource(base):
    def __repr__(self):
        return "<Resource %s>" % self._info

    @property
    def stack_name(self):
        if not hasattr(self, 'links'):
            return
        for l in self.links:
            if l['rel'] == 'stack':
                return l['href'].split('/')[-2]


class API(object):
    def __init__(self):
        self.api = engine.EngineService(utils.get_hostid(),
                                        rpc_api.ENGINE_TOPIC)

    def _extract_int_param(self, name, value,
                           allow_zero=True, allow_negative=False):
        try:
            return param_utils.extract_int(name, value,
                                           allow_zero, allow_negative)
        except ValueError as e:
            raise exc.HTTPBadRequest(six.text_type(e))

    def _extract_tags_param(self, tags):
        try:
            return param_utils.extract_tags(tags)
        except ValueError as e:
            raise exc.HTTPBadRequest(six.text_type(e))

    def prepare_args(self, data):
        args = data.args()
        key = rpc_api.PARAM_TIMEOUT
        if key in args:
            args[key] = self._extract_int_param(key, args[key])
        key = rpc_api.PARAM_TAGS
        if args.get(key) is not None:
            args[key] = self._extract_tags_param(args[key])
        return args

    def _make_identity(self, tenant, stack_name, stack_id):
        stack_identity = {'tenant': tenant,
                          'stack_name': stack_name,
                          'stack_id': stack_id}
        return stack_identity
    
    def get_stack(self, context, stack_id):
        # context._session = db_api.get_session()
        # stack_identity = self._make_identity(context.project_id,
        #                                      '', stack_id)
        # stack_list = engineclient(context).show_stack(context, stack_identity)
        # context._session = db_api.get_session()
        stack_list = db_api.stack_get(context, stack_id,
                                      {'show_deleted': False, 'eager_load': True})
        if not stack_list:
            return None
        stack_list[rpc_api.STACK_STATUS] = stack_list['status']
        stack_list[rpc_api.STACK_ACTION] = stack_list['action']
        # stack_list = stack_list[0]
        return Stack(format_stack(stack_list))

    def _wait_for_resource(self, context, stack_id):
        """Called at an interval until the resources are deleted ."""
        st = self.get_stack(context, stack_id)
        state = st.stack_status
        if state in ["DELETE_RES_COMPLETE", "DELETE_FAILED"]:
            LOG.info("clear table or resource deployed: %s.", state)
            raise loopingcall.LoopingCallDone()

    def _wait_for_table(self, context, stack_id):
        """Called at an interval until the resources are deleted ."""
        st = self.get_stack(context, stack_id)
        state = st.stack_status
        if state in ["DELETE_COMPLETE", "DELETE_FAILED"]:
            LOG.info("clear table or resource deployed: %s.", state)
            raise loopingcall.LoopingCallDone()

    def clear_resource(self, context, stack_id, plan_id, is_heat_stack=False):
        # need stackname not id
        # context._session = db_api.get_session()
        try:
            stacks = db_api.plan_stack_get(context, plan_id)
            values = {'deleted': True, 'updated_at': timeutils.utcnow()}
            for st in stacks[::-1]:
                stack_identity = self._make_identity(context.project_id,
                                                     '', st['stack_id'])
                # context._session = db_api.get_session()
                self.api.clear_resource(context, stack_identity)
                loop_fun = functools.partial(self._wait_for_resource, context,
                                             st['stack_id'])
                timer = loopingcall.FixedIntervalLoopingCall(loop_fun)
                timer.start(interval=0.5).wait()
                db_api.plan_stack_update(context, plan_id, st['stack_id'], values)
            # context._session = db_api.get_session()
            # db_api.plan_stack_delete(context, plan_id)
        except Exception as e:
            LOG.error("clear resource fail")
            raise

    def clear_table(self, context, stack_id, plan_id, is_heat_stack=False):
        # need stackname not id
        # context._session = db_api.get_session()
        try:
            stacks = db_api.plan_stack_get(context, plan_id, read_deleted='yes')
            for st in stacks[::-1]:
                stack_identity = self._make_identity(context.project_id,
                                                     '', st['stack_id'])
                # context._session = db_api.get_session()
                self.api.clear_table(context, stack_identity)
                loop_fun = functools.partial(self._wait_for_table, context,
                                             st['stack_id'])
                timer = loopingcall.FixedIntervalLoopingCall(loop_fun)
                timer.start(interval=0.5).wait()
                # context._session = db_api.get_session()
                db_api.plan_stack_delete(context, plan_id, st['stack_id'])
        except Exception as e:
            LOG.error("clear table fail")
            raise
    
    def delete_stack(self, context, stack_id, plan_id, is_heat_stack=False):
        # need stackname not id
        # context._session = db_api.get_session()
        try:
            stacks = db_api.plan_stack_get(context, plan_id, read_deleted='yes')
            for st in stacks[::-1]:
                stack_identity = self._make_identity(context.project_id,
                                                     '', st['stack_id'])
                # context._session = db_api.get_session()
                self.api.delete_stack(context, stack_identity)
                loop_fun = functools.partial(self._wait_for_finish, context,
                                             st['stack_id'])
                timer = loopingcall.FixedIntervalLoopingCall(loop_fun)
                timer.start(interval=0.5).wait()
                db_api.plan_stack_delete(context, plan_id, st['stack_id'])
            # context._session = db_api.get_session()
            # db_api.plan_stack_delete_all(context, plan_id)
        except Exception as e:
            LOG.error("delete stack fail")
            raise

    def create_stack(self, context, password=None, **kwargs):
        # context._session = db_api.get_session()
        data = InstantiationData(kwargs)
        args = self.prepare_args(data)
        result = self.api.create_stack(context, data.stack_name(),
                                       data.template(), data.environment(),
                                       data.files(), args,
                                       environment_files=data.environment_files())
        formatted_stack = format_stack(
            {rpc_api.STACK_ID: result}
        )
        LOG.debug("create stack with formatted_stack=%s", formatted_stack)
        return {'stack': formatted_stack}

    def preview_stack(self, context, password=None, **kwargs):
        # context._session = db_api.get_session()
        data = InstantiationData(kwargs)
        args = self.prepare_args(data)
        stacks = self.api.preview_stack(context, data.stack_name(),
                                        data.template(), data.environment(),
                                        data.files(), args,
                                        environment_files=
                                        data.environment_files())
        return Stack(format_stack(stacks))
    
    def resources_list(self, context, stack_name):
        # context._session = db_api.get_session()
        stack_identity = self._make_identity(context.project_id,
                                             '', stack_name)
        res_list = self.api.list_stack_resources(context, stack_identity)
        data = [format_resource(res) for res in res_list]
        return [Event(res) for res in data]

    def get_resource(self, context, stack_id, resource_name):
        # context._session = db_api.get_session()
        stack_identity = self._make_identity(context.project_id,
                                             '', stack_id)
        res = self.api.describe_stack_resource(context, stack_identity,
                                               resource_name)
        return Resource(format_resource(res))

    def get_resource_type(self, context, resource_type):
        # context._session = db_api.get_session()
        return self.api.resource_schema(context, resource_type)
    
    def events_list(self, context, stack_id):
        # context._session = db_api.get_session()
        # hc = heatclient(context)
        # stack_identity = self._make_identity(context.project_id,
        #                                      '', stack_id)
        # events = hc.list_events(context, stack_identity)
        events = db_api.event_get_all_by_stack(context, stack_id)
        if not events:
            return None
        data = [format_event(e) for e in events]
        # data = data['values']
        return [Event(res) for res in data]
    
    def get_event(self, context, stack_id, resource_name, event_id):
        # context._session = db_api.get_session()
        stack_identity = self._make_identity(context.project_id,
                                             '', stack_id)
        filters = {"resource_name": resource_name, "uuid": event_id}
        events = self.api.list_events(context, stack_identity, filters=filters)
        if not events:
            return None
        return Event(events)

    def get_template(self, context, stack_id):
        # context._session = db_api.get_session()
        stack_identity = self._make_identity(context.project_id,
                                             '', stack_id)
        return self.api.get_template(context, stack_identity)
    
    def stack_list(self, context, **kwargs):
        # context._session = db_api.get_session()
        stacks = self.api.list_stacks(context, **kwargs)
        data = [format_stack(s) for s in stacks]
        return [Stack(s) for s in data]
