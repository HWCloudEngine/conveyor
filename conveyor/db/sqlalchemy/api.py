# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

"""Implementation of SQLAlchemy backend."""

import datetime
import functools
import sys
import threading
import time

import six
from oslo_config import cfg
from oslo_db import exception as db_exc
from oslo_db.sqlalchemy import session as db_session
from oslo_log import log as logging

import conveyor.context
from conveyor import exception as conveyor_exception
from conveyor.db.sqlalchemy import models, utils
from conveyor.i18n import _
from conveyor.i18n import _LE

# add from heat
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslo_db import api as oslo_db_api
from oslo_db.sqlalchemy import utils
from oslo_utils import encodeutils

import sqlalchemy
from sqlalchemy import func
from sqlalchemy import orm
from sqlalchemy.orm import aliased as orm_aliased
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.orm import session as orm_session

import osprofiler.sqlalchemy
from conveyor.common import sqlalchemyutils
from conveyor.conveyorheat.common import crypt
from conveyor.conveyorheat.common import exception
from conveyor.db.sqlalchemy import filters as db_filters
from conveyor import exception
import migration
# from conveyor.db.sqlalchemy import models
from conveyor.db.sqlalchemy import utils as db_utils
from conveyor.conveyorheat.engine import environment as heat_environment
from conveyor.conveyorheat.rpc import api as rpc_api

db_opts = [
    cfg.StrOpt('birdie_api_name_scope',
               default='',
               help='When set, compute API will consider duplicate hostnames '
                    'invalid within the specified scope, regardless of case. '
                    'Should be empty, "project" or "global".'),
]

CONF = cfg.CONF
CONF.register_opts(db_opts)
# CONF = cfg.CONF
CONF.import_opt('hidden_stack_tags',
                'conveyor.conveyorheat.common.config')
CONF.import_opt('max_events_per_stack',
                'conveyor.conveyorheat.common.config')
CONF.import_group('profiler',
                  'conveyor.conveyorheat.common.config')

LOG = logging.getLogger(__name__)
# LOG.basicConfig(filename='myapp.log', level=LOG.INFO)


_ENGINE_FACADE = None
_facade = None
_LOCK = threading.Lock()


def _create_facade_lazily():
    global _LOCK, _ENGINE_FACADE
    if _ENGINE_FACADE is None:
        with _LOCK:
            if _ENGINE_FACADE is None:
                _ENGINE_FACADE = db_session.EngineFacade.from_config(CONF)
    return _ENGINE_FACADE
    # global _facade
    #
    # if not _facade:
    #     _facade = db_session.EngineFacade.from_config(CONF)
    #     if CONF.profiler.enabled:
    #         if CONF.profiler.trace_sqlalchemy:
    #             osprofiler.sqlalchemy.add_tracing(sqlalchemy,
    #                                               _facade.get_engine(),
    #                                               "db")
    #
    # return _facade


def get_engine(use_slave=False):
    facade = _create_facade_lazily()
    return facade.get_engine()
    # return facade.get_engine(use_slave=use_slave)


def get_session(use_slave=False, **kwargs):
    facade = _create_facade_lazily()
    return facade.get_session()
    # return facade.get_session(use_slave=use_slave, **kwargs)


# def get_session_heat():
#     return get_facade().get_session()


_SHADOW_TABLE_PREFIX = 'shadow_'
_DEFAULT_QUOTA_NAME = 'default'


def get_backend():
    """The backend is this module itself."""
    return sys.modules[__name__]


def require_context(f):
    """Decorator to require *any* plan or admin context.

    This does no authorization for plan or project access matching, see
    :py:func:`conveyor.authorize_project_context` and
    :py:func:`conveyor.context.authorize_user_context`.

    The first argument to the wrapped function must be the context.

    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        conveyor.context.require_context(args[0])
        return f(*args, **kwargs)
    return wrapper


def _retry_on_deadlock(f):
    """Decorator to retry a DB API call if Deadlock was received."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        while True:
            try:
                return f(*args, **kwargs)
            except db_exc.DBDeadlock:
                LOG.warn(_("Deadlock detected when running "
                           "'%(func_name)s': Retrying..."),
                           dict(func_name=f.__name__))
                # Retry!
                time.sleep(0.5)
                continue
    functools.update_wrapper(wrapped, f)
    return wrapped


def model_query_heat_original(context, *args):
    session = _session(context)
    session.begin(subtransactions=True)
    query = session.query(*args)
    session.commit()
    return query


def model_query_heat(context, model, *args, **kwargs):
    # session = _session(context)
    # with session.begin():
    #     query = session.query(*args)
    # return query
    use_slave = kwargs.get('use_slave') or False
    if CONF.database.slave_connection == '':
        use_slave = False

    session = get_session()
    # session = kwargs.get('session') or get_session(use_slave=use_slave)
    # read_deleted = kwargs.get('read_deleted') or context.read_deleted

    def issubclassof_gw_base(obj):
        return isinstance(obj, type) and issubclass(obj, models.CopyBase)

    base_model = model
    if not issubclassof_gw_base(base_model):
        base_model = kwargs.get('base_model', None)
        if not issubclassof_gw_base(base_model):
            raise Exception(_("model or base_model parameter should be "
                              "subclass of CopyBase"))

    session.begin(subtransactions=True)
    query = session.query(model, *args)
    session.commit()
    return query


def model_query(context, model, *args, **kwargs):
    """Query helper that accounts for context's `read_deleted` field.

    :param context: context to query under
    :param use_slave: If true, use slave_connection
    :param session: if present, the session to use
    :param read_deleted: if present, overrides context's read_deleted field.
    :param project_only: if present and context is plan-type, then restrict
            query to match the context's project_id. If set to 'allow_none',
            restriction includes project_id = None.
    :param base_model: Where model_query is passed a "model" parameter which is
            not a subclass of ConveyorBase, we should pass an extra base_model
            parameter that is a subclass of ConveyorBase and corresponds to the
            model parameter.
    """

    use_slave = kwargs.get('use_slave') or False
    if CONF.database.slave_connection == '':
        use_slave = False

    session = kwargs.get('session') or get_session(use_slave=use_slave)
    read_deleted = kwargs.get('read_deleted') or context.read_deleted

    def issubclassof_gw_base(obj):
        return isinstance(obj, type) and issubclass(obj, models.ConveyorBase)

    base_model = model
    if not issubclassof_gw_base(base_model):
        base_model = kwargs.get('base_model', None)
        if not issubclassof_gw_base(base_model):
            raise Exception(_("model or base_model parameter should be "
                              "subclass of ConveyorBase"))

    query = session.query(model, *args)

    default_deleted_value = base_model.__mapper__.c.deleted.default.arg
    if read_deleted == 'no':
        query = query.filter(base_model.deleted == default_deleted_value)
    elif read_deleted == 'yes':
        pass  # omit the filter to include deleted and active
    elif read_deleted == 'only':
        query = query.filter(base_model.deleted != default_deleted_value)
    else:
        raise Exception(_("Unrecognized read_deleted value '%s'")
                            % read_deleted)

    return query

###################


@require_context
def _plan_get_query(context, session=None):
    """Get the query to retrieve the Plan.

    :param context: the context used to run the method _plan_get_query
    :param session: the session to use
    :param project_only: the boolean used to decide whether to query the
                         Plan in the current project or all projects
    :param joined_load: the boolean used to decide whether the query loads
                        the other models, which join the Plan model in
                        the database. Currently, the False value for this
                        parameter is specially for the case of updating
                        database during Plan migration
    :returns: updated query or None
    """
    return model_query(context, models.Plan, session=session)


def _plan_get(context, id, session=None, read_deleted='no'):
    result = model_query(context, models.Plan, session=session, read_deleted='no').\
               filter_by(plan_id=id).\
                first()
    if not result:
        raise conveyor_exception.PlanNotFoundInDb(id = id)
    return result


@require_context
def plan_get(context, id):
    try: 
        result = _plan_get(context, id)
    except db_exc.DBError:
        msg = _("Invalid plan id %s in request") % id
        LOG.warn(msg)
        raise conveyor_exception.InvalidID(id=id)
    return dict(result)


@require_context
def plan_create(context, values):
    plan_ref = models.Plan()
    plan_ref.update(values)
    try:
        plan_ref.save()
    except db_exc.DBDuplicateEntry as e:
        raise conveyor_exception.PlanExists( id=values.get('id'))
    except db_exc.DBReferenceError as e:
        raise conveyor_exception.IntegrityException(msg=str(e))
    except db_exc.DBError as e:
        LOG.exception('DB error:%s', e)
        raise conveyor_exception.PlanCreateFailed()
    return dict(plan_ref)


@require_context
def plan_update(context, id, values):
    session = get_session()
    with session.begin():
        plan_ref = _plan_get(context, id, session=session)
        if not plan_ref:
            raise conveyor_exception.PlanNotFoundInDb(id=id)
        plan_ref.update(values)
        try:
            plan_ref.save(session=session)
        except db_exc.DBDuplicateEntry:
            raise conveyor_exception.PlanExists()

    return dict(plan_ref)


@require_context
def plan_get_all(context, marker=None, limit=None, sort_keys=None,
                 sort_dirs=None, filters=None):
    """Retrieves all plans.

    If no sort parameters are specified then the returned Plans are sorted
    first by the 'created_at' key and then by the 'id' key in descending
    order.

    :param context: context to query under
    :param marker: the last item of the previous page, used to determine the
                   next page of results to return
    :param limit: maximum number of items to return
    :param sort_keys: list of attributes by which results should be sorted,
                      paired with corresponding item in sort_dirs
    :param sort_dirs: list of directions in which results should be sorted,
                      paired with corresponding item in sort_keys
    :param filters: dictionary of filters; values that are in lists, tuples,
                    or sets cause an 'IN' operation, while exact matching
                    is used for other values, see _process_plan_filters
                    function for more information
    :returns: list of matching plans
    """
    session = get_session()
    with session.begin():
        # Generate the query
        query = _generate_paginate_query(context, session, marker, limit,
                                         sort_keys, sort_dirs, filters)
        # No Plans would match, return empty list
        if query is None:
            return []
        return query.all()


def _generate_paginate_query(context, session, marker, limit, sort_keys,
                             sort_dirs, filters, offset=None,
                             paginate_type=models.Plan):
    """Generate the query to include the filters and the paginate options.

    Returns a query with sorting / pagination criteria added or None
    if the given filters will not yield any results.

    :param context: context to query under
    :param session: the session to use
    :param marker: the last item of the previous page; we returns the next
                    results after this value.
    :param limit: maximum number of items to return
    :param sort_keys: list of attributes by which results should be sorted,
                      paired with corresponding item in sort_dirs
    :param sort_dirs: list of directions in which results should be sorted,
                      paired with corresponding item in sort_keys
    :param filters: dictionary of filters; values that are in lists, tuples,
                    or sets cause an 'IN' operation, while exact matching
                    is used for other values, see _process_Plan_filters
                    function for more information
    :param offset: number of items to skip
    :param paginate_type: type of pagination to generate
    :returns: updated query or None
    """
    get_query, process_filters, get = PAGINATION_HELPERS[paginate_type]

    sort_keys, sort_dirs = process_sort_params(sort_keys,
                                               sort_dirs,
                                               default_dir='desc')
    query = get_query(context, session=session)

    if filters:
        query = process_filters(query, filters)
        if query is None:
            return None

    marker_object = None
    if marker is not None:
        marker_object = get(context, marker, session)

    return sqlalchemyutils.paginate_query(query, paginate_type, limit,
                                          sort_keys,
                                          marker=marker_object,
                                          sort_dirs=sort_dirs,
                                          offset=offset)


def _process_plan_filters(query, filters):
    """Common filter processing for Plan queries.

    Filter values that are in lists, tuples, or sets cause an 'IN' operator
    to be used, while exact matching ('==' operator) is used for other values.

    A filter key/value of 'no_migration_targets'=True causes Plans with
    either a NULL 'migration_status' or a 'migration_status' that does not
    start with 'target:' to be retrieved.

    A 'metadata' filter key must correspond to a dictionary value of metadata
    key-value pairs.

    :param query: Model query to use
    :param filters: dictionary of filters
    :returns: updated query or None
    """
    filters = filters.copy()

    # Apply exact match filters for everything else, ensure that the
    # filter value exists on the model
    for key in filters.keys():
        try:
            column_attr = getattr(models.Plan, key)
            # Do not allow relationship properties since those require
            # schema specific knowledge
            prop = getattr(column_attr, 'property')
            if isinstance(prop, RelationshipProperty):
                LOG.debug(("'%s' filter key is not valid, "
                           "it maps to a relationship."), key)
                return None
        except AttributeError:
            LOG.debug("'%s' filter key is not valid.", key)
            return None

    # Holds the simple exact matches
    filter_dict = {}

    # Iterate over all filters, special case the filter if necessary
    for key, value in filters.items():
        if isinstance(value, (list, tuple, set, frozenset)):
            # Looking for values in a list; apply to query directly
            column_attr = getattr(models.Plan, key)
            query = query.filter(column_attr.in_(value))
        else:
            # OK, simple exact match; save for later
            filter_dict[key] = value

    # Apply simple exact matches
    if filter_dict:
        query = query.filter_by(**filter_dict)
    return query


def process_sort_params(sort_keys, sort_dirs, default_keys=None,
                        default_dir='asc'):
    """Process the sort parameters to include default keys.

    Creates a list of sort keys and a list of sort directions. Adds the default
    keys to the end of the list if they are not already included.

    When adding the default keys to the sort keys list, the associated
    direction is:
    1) The first element in the 'sort_dirs' list (if specified), else
    2) 'default_dir' value (Note that 'asc' is the default value since this is
    the default in sqlalchemy.utils.paginate_query)

    :param sort_keys: List of sort keys to include in the processed list
    :param sort_dirs: List of sort directions to include in the processed list
    :param default_keys: List of sort keys that need to be included in the
                         processed list, they are added at the end of the list
                         if not already specified.
    :param default_dir: Sort direction associated with each of the default
                        keys that are not supplied, used when they are added
                        to the processed list
    :returns: list of sort keys, list of sort directions
    :raise exception.InvalidInput: If more sort directions than sort keys
                                   are specified or if an invalid sort
                                   direction is specified
    """
    if default_keys is None:
        default_keys = ['created_at', 'id']

    # Determine direction to use for when adding default keys
    if sort_dirs and len(sort_dirs):
        default_dir_value = sort_dirs[0]
    else:
        default_dir_value = default_dir

    # Create list of keys (do not modify the input list)
    if sort_keys:
        result_keys = list(sort_keys)
    else:
        result_keys = []

    # If a list of directions is not provided, use the default sort direction
    # for all provided keys.
    if sort_dirs:
        result_dirs = []
        # Verify sort direction
        for sort_dir in sort_dirs:
            if sort_dir not in ('asc', 'desc'):
                msg = _("Unknown sort direction, must be 'desc' or 'asc'.")
                raise exception.InvalidInput(reason=msg)
            result_dirs.append(sort_dir)
    else:
        result_dirs = [default_dir_value for _sort_key in result_keys]

    # Ensure that the key and direction length match
    while len(result_dirs) < len(result_keys):
        result_dirs.append(default_dir_value)
    # Unless more direction are specified, which is an error
    if len(result_dirs) > len(result_keys):
        msg = _("Sort direction array size exceeds sort key array size.")
        raise exception.InvalidInput(reason=msg)

    # Ensure defaults are included
    for key in default_keys:
        if key not in result_keys:
            result_keys.append(key)
            result_dirs.append(default_dir_value)

    return result_keys, result_dirs


def plan_delete(context, id):
    session = get_session()
    with session.begin():
        plan_ref = _plan_get(context, id, session=session)
        # if not plan_ref: raise conveyor_exception.planNotFound(id=id)
        #plan_ref.soft_delete(session=session)
        session.delete(plan_ref)


@require_context
def plan_stack_create(context, values):
    stack_ref = models.PlanStack()
    stack_ref.update(values)
    try:
        stack_ref.save()
    except db_exc.DBDuplicateEntry as e:
        raise conveyor_exception.PlanExists(id=values.get('id'))
    except db_exc.DBReferenceError as e:
        raise conveyor_exception.IntegrityException(msg=str(e))
    except db_exc.DBError as e:
        LOG.exception('DB error:%s', e)
        raise conveyor_exception.PlanCreateFailed()
    return dict(stack_ref)


@require_context
def plan_stack_get(context, plan_id, session=None):
    results = (model_query(context, models.PlanStack, session=session)
               .filter_by(plan_id=plan_id)
               .all())
    return results


@require_context
def plan_stack_delete(context, plan_id):
    session = get_session()
    with session.begin():
        ps = plan_stack_get(context, plan_id, session=session)
        if not ps:
            raise exception.NotFound(_('Attempt to delete plan_id: '
                                       '%(id)s %(msg)s') % {
                                         'id': plan_id,
                                         'msg': 'that does not exist'})
        for p in ps:
            session.delete(p)


# add from heat
# _facade = None
#
#
# def get_facade():
#     global _facade
#
#     if not _facade:
#         _facade = db_session.EngineFacade.from_config(CONF)
#         if CONF.profiler.enabled:
#             if CONF.profiler.trace_sqlalchemy:
#                 osprofiler.sqlalchemy.add_tracing(sqlalchemy,
#                                                   _facade.get_engine(),
#                                                   "db")
#
#     return _facade


def soft_delete_aware_query(context, *args, **kwargs):
    """Stack query helper that accounts for context's `show_deleted` field.

    :param show_deleted: if True, overrides context's show_deleted field.
    """

    query = model_query_heat(context, *args)
    show_deleted = kwargs.get('show_deleted') or context.show_deleted

    if not show_deleted:
        query = query.filter_by(deleted_at=None)
    return query


def _session(context=None):
    # return get_session()
    # return get_session()
    return (context and context.session) or get_session()
    # return (context and context.session) or get_session_heat()
    # return get_session(use_slave=False)


def raw_template_get(context, template_id):
    result = model_query_heat(context, models.RawTemplate).get(template_id)

    if not result:
        raise exception.NotFound(_('raw template with id %s not found') %
                                 template_id)
    return result


def raw_template_create(context, values):
    raw_template_ref = models.RawTemplate()
    raw_template_ref.update(values)
    raw_template_ref.save(_session(context))
    return raw_template_ref


def raw_template_update(context, template_id, values):
    raw_template_ref = raw_template_get(context, template_id)
    # get only the changed values
    values = dict((k, v) for k, v in values.items()
                  if getattr(raw_template_ref, k) != v)

    if values:
        raw_template_ref.update_and_save(values)

    return raw_template_ref


def raw_template_delete(context, template_id):
    raw_template = raw_template_get(context, template_id)
    raw_template.delete()


def resource_get(context, resource_id):
    # result = model_query_heat(context, models.Resource).get(resource_id)
    result = model_query_heat_original(context, models.Resource).get(resource_id)
    if not result:
        raise exception.NotFound(_("resource with id %s not found") %
                                 resource_id)
    return result


def resource_get_by_name_and_stack(context, resource_name, stack_id):
    result = model_query_heat(
        context, models.Resource
    ).filter_by(
        name=resource_name
    ).filter_by(
        stack_id=stack_id
    ).options(orm.joinedload("data")).first()
    return result


def resource_get_by_physical_resource_id(context, physical_resource_id):
    results = (model_query_heat(context, models.Resource)
               .filter_by(nova_instance=physical_resource_id)
               .all())

    for result in results:
        if context is None or context.tenant_id in (
                result.stack.tenant, result.stack.stack_user_project_id):
            return result
    return None


def resource_get_all(context):
    results = model_query_heat(context, models.Resource).all()

    if not results:
        raise exception.NotFound(_('no resources were found'))
    return results


def resource_update(context, resource_id, values, atomic_key,
                    expected_engine_id=None):
    session = _session(context)
    with session.begin():
        if atomic_key is None:
            values['atomic_key'] = 1
        else:
            values['atomic_key'] = atomic_key + 1
        rows_updated = session.query(models.Resource).filter_by(
            id=resource_id, engine_id=expected_engine_id,
            atomic_key=atomic_key).update(values)

        return bool(rows_updated)


def resource_data_get_all(context, resource_id, data=None):
    """Looks up resource_data by resource.id.

    If data is encrypted, this method will decrypt the results.
    """
    if data is None:
        data = (model_query_heat(context, models.ResourceData)
                .filter_by(resource_id=resource_id)).all()

    if not data:
        raise exception.NotFound(_('no resource data found'))

    ret = {}

    for res in data:
        if res.redact:
            ret[res.key] = crypt.decrypt(res.decrypt_method, res.value)
        else:
            ret[res.key] = res.value
    return ret


def resource_data_get(resource, key):
    """Lookup value of resource's data by key.

    Decrypts resource data if necessary.
    """
    result = resource_data_get_by_key(resource.context,
                                      resource.id,
                                      key)
    if result.redact:
        return crypt.decrypt(result.decrypt_method, result.value)
    return result.value


def stack_tags_set(context, stack_id, tags):
    session = _session(context)
    with session.begin():
        stack_tags_delete(context, stack_id)
        result = []
        for tag in tags:
            stack_tag = models.StackTag()
            stack_tag.tag = tag
            stack_tag.stack_id = stack_id
            stack_tag.save(session=session)
            result.append(stack_tag)
        return result or None


def stack_tags_delete(context, stack_id):
    session = _session(context)
    with session.begin(subtransactions=True):
        result = stack_tags_get(context, stack_id)
        if result:
            for tag in result:
                tag.delete()


def stack_tags_get(context, stack_id):
    result = (model_query_heat(context, models.StackTag)
              .filter_by(stack_id=stack_id)
              .all())
    return result or None


def resource_data_get_by_key(context, resource_id, key):
    """Looks up resource_data by resource_id and key.

    Does not decrypt resource_data.
    """
    result = (model_query_heat(context, models.ResourceData)
              .filter_by(resource_id=resource_id)
              .filter_by(key=key).first())

    if not result:
        raise exception.NotFound(_('No resource data found'))
    return result


def resource_data_set(resource, key, value, redact=False):
    """Save resource's key/value pair to database."""
    if redact:
        method, value = crypt.encrypt(value)
    else:
        method = ''
    try:
        current = resource_data_get_by_key(resource.context, resource.id, key)
    except exception.NotFound:
        current = models.ResourceData()
        current.key = key
        current.resource_id = resource.id
    current.redact = redact
    current.value = value
    current.decrypt_method = method
    current.save(session=resource.context.session)
    return current


def resource_exchange_stacks(context, resource_id1, resource_id2):
    query = model_query_heat(context, models.Resource)
    session = query.session
    session.begin()

    res1 = query.get(resource_id1)
    res2 = query.get(resource_id2)

    res1.stack, res2.stack = res2.stack, res1.stack

    session.commit()


def resource_data_delete(resource, key):
    result = resource_data_get_by_key(resource.context, resource.id, key)
    result.delete()


def resource_create(context, values):
    resource_ref = models.Resource()
    resource_ref.update(values)
    resource_ref.save(_session(context))
    return resource_ref


def resource_get_all_by_stack(context, stack_id, key_id=False, filters=None):
    query = model_query_heat(
        context, models.Resource
    ).filter_by(
        stack_id=stack_id
    ).options(orm.joinedload("data"))

    query = db_filters.exact_filter(query, models.Resource, filters)
    results = query.all()

    if not results:
        raise exception.NotFound(_("no resources for stack_id %s were found")
                                 % stack_id)
    if key_id:
        return dict((res.id, res) for res in results)
    else:
        return dict((res.name, res) for res in results)


def stack_get_by_name_and_owner_id(context, stack_name, owner_id):
    query = soft_delete_aware_query(
        context, models.Stack
    ).filter(sqlalchemy.or_(
             models.Stack.tenant == context.tenant_id,
             models.Stack.stack_user_project_id == context.tenant_id)
             ).filter_by(name=stack_name).filter_by(owner_id=owner_id)
    return query.first()


def stack_get_by_name(context, stack_name):
    query = soft_delete_aware_query(
        context, models.Stack
    ).filter(sqlalchemy.or_(
             models.Stack.tenant == context.tenant_id,
             models.Stack.stack_user_project_id == context.tenant_id)
             ).filter_by(name=stack_name)
    return query.first()


def stack_get(context, stack_id, show_deleted=False, tenant_safe=True,
              eager_load=False):
    # query = model_query_heat_original(context, models.Stack)
    # if eager_load:
    #     query = query.options(orm.joinedload("raw_template"))
    # result = query.get(stack_id)
    result = model_query_heat(context, models.Stack).filter_by(id=stack_id).first()

    deleted_ok = show_deleted or context.show_deleted
    if result is None or result.deleted_at is not None and not deleted_ok:
        return None

    # One exception to normal project scoping is users created by the
    # stacks in the stack_user_project_id (in the heat stack user domain)
    if (tenant_safe and result is not None and context is not None and
        context.tenant_id not in (result.tenant,
                                  result.stack_user_project_id)):
        return None
    return result


def stack_get_status(context, stack_id):
    query = model_query_heat(context, models.Stack)
    query = query.options(
        orm.load_only("action", "status", "status_reason", "updated_at"))
    result = query.filter_by(id=stack_id).first()
    if result is None:
        raise exception.NotFound(_('Stack with id %s not found') % stack_id)

    return (result.action, result.status, result.status_reason,
            result.updated_at)


def stack_get_all_by_owner_id(context, owner_id):
    results = soft_delete_aware_query(
        context, models.Stack).filter_by(owner_id=owner_id).all()
    return results


def _get_sort_keys(sort_keys, mapping):
    """Returns an array containing only whitelisted keys

    :param sort_keys: an array of strings
    :param mapping: a mapping from keys to DB column names
    :returns: filtered list of sort keys
    """
    if isinstance(sort_keys, six.string_types):
        sort_keys = [sort_keys]
    return [mapping[key] for key in sort_keys or [] if key in mapping]


def _paginate_query(context, query, model, limit=None, sort_keys=None,
                    marker=None, sort_dir=None):
    default_sort_keys = ['created_at']
    if not sort_keys:
        sort_keys = default_sort_keys
        if not sort_dir:
            sort_dir = 'desc'

    # This assures the order of the stacks will always be the same
    # even for sort_key values that are not unique in the database
    sort_keys = sort_keys + ['id']

    model_marker = None
    if marker:
        model_marker = model_query_heat(context, model).get(marker)
    try:
        query = utils.paginate_query(query, model, limit, sort_keys,
                                     model_marker, sort_dir)
    except utils.InvalidSortKey as exc:
        err_msg = encodeutils.exception_to_unicode(exc)
        raise exception.Invalid(reason=err_msg)
    return query


def _query_stack_get_all(context, tenant_safe=True, show_deleted=False,
                         show_nested=False, show_hidden=False, tags=None,
                         tags_any=None, not_tags=None, not_tags_any=None):
    if show_nested:
        query = soft_delete_aware_query(
            context, models.Stack, show_deleted=show_deleted
        ).filter_by(backup=False)
    else:
        query = soft_delete_aware_query(
            context, models.Stack, show_deleted=show_deleted
        ).filter_by(owner_id=None)

    if tenant_safe:
        query = query.filter_by(tenant=context.tenant_id)

    if tags:
        for tag in tags:
            tag_alias = orm_aliased(models.StackTag)
            query = query.join(tag_alias, models.Stack.tags)
            query = query.filter(tag_alias.tag == tag)

    if tags_any:
        query = query.filter(
            models.Stack.tags.any(
                models.StackTag.tag.in_(tags_any)))

    if not_tags:
        subquery = soft_delete_aware_query(
            context, models.Stack, show_deleted=show_deleted
        )
        for tag in not_tags:
            tag_alias = orm_aliased(models.StackTag)
            subquery = subquery.join(tag_alias, models.Stack.tags)
            subquery = subquery.filter(tag_alias.tag == tag)
        not_stack_ids = [s.id for s in subquery.all()]
        query = query.filter(models.Stack.id.notin_(not_stack_ids))

    if not_tags_any:
        query = query.filter(
            ~models.Stack.tags.any(
                models.StackTag.tag.in_(not_tags_any)))

    if not show_hidden and cfg.CONF.hidden_stack_tags:
        query = query.filter(
            ~models.Stack.tags.any(
                models.StackTag.tag.in_(cfg.CONF.hidden_stack_tags)))

    return query


def stack_get_all(context, limit=None, sort_keys=None, marker=None,
                  sort_dir=None, filters=None, tenant_safe=True,
                  show_deleted=False, show_nested=False, show_hidden=False,
                  tags=None, tags_any=None, not_tags=None,
                  not_tags_any=None):
    query = _query_stack_get_all(context, tenant_safe,
                                 show_deleted=show_deleted,
                                 show_nested=show_nested,
                                 show_hidden=show_hidden, tags=tags,
                                 tags_any=tags_any, not_tags=not_tags,
                                 not_tags_any=not_tags_any)
    return _filter_and_page_query(context, query, limit, sort_keys,
                                  marker, sort_dir, filters).all()


def _filter_and_page_query(context, query, limit=None, sort_keys=None,
                           marker=None, sort_dir=None, filters=None):
    if filters is None:
        filters = {}

    sort_key_map = {rpc_api.STACK_NAME: models.Stack.name.key,
                    rpc_api.STACK_STATUS: models.Stack.status.key,
                    rpc_api.STACK_CREATION_TIME: models.Stack.created_at.key,
                    rpc_api.STACK_UPDATED_TIME: models.Stack.updated_at.key}
    whitelisted_sort_keys = _get_sort_keys(sort_keys, sort_key_map)

    query = db_filters.exact_filter(query, models.Stack, filters)
    return _paginate_query(context, query, models.Stack, limit,
                           whitelisted_sort_keys, marker, sort_dir)


def stack_count_all(context, filters=None, tenant_safe=True,
                    show_deleted=False, show_nested=False, show_hidden=False,
                    tags=None, tags_any=None, not_tags=None,
                    not_tags_any=None):
    query = _query_stack_get_all(context, tenant_safe=tenant_safe,
                                 show_deleted=show_deleted,
                                 show_nested=show_nested,
                                 show_hidden=show_hidden, tags=tags,
                                 tags_any=tags_any, not_tags=not_tags,
                                 not_tags_any=not_tags_any)
    query = db_filters.exact_filter(query, models.Stack, filters)
    return query.count()


def stack_create(context, values):
    stack_ref = models.Stack()
    stack_ref.update(values)
    stack_ref.save(_session(context))
    return stack_ref


def stack_update(context, stack_id, values, exp_trvsl=None):
    stack = stack_get(context, stack_id)

    if stack is None:
        raise exception.NotFound(_('Attempt to update a stack with id: '
                                 '%(id)s %(msg)s') % {
                                     'id': stack_id,
                                     'msg': 'that does not exist'})

    if (exp_trvsl is not None
            and stack.current_traversal != exp_trvsl):
        # stack updated by another update
        return False

    # session = _session(context)
    session = get_session()

    with session.begin(subtransactions=True):
        rows_updated = (session.query(models.Stack)
                        .filter(models.Stack.id == stack.id)
                        .filter(models.Stack.current_traversal\
                                == stack.current_traversal)
                        .update(values, synchronize_session=False))
    session.expire_all()
    return (rows_updated is not None and rows_updated > 0)


def stack_delete(context, stack_id):
    # s = stack_get(context, stack_id)
    session = get_session()
    s = session.query(models.Stack). \
        filter(models.Stack.id == stack_id).first()
    # query = model_query_heat_original(context, models.Stack)
    # s = query.get(stack_id)
    if not s:
        raise exception.NotFound(_('Attempt to delete a stack with id: '
                                 '%(id)s %(msg)s') % {
                                     'id': stack_id,
                                     'msg': 'that does not exist'})
    # session = orm_session.Session.object_session(s)
    for r in s.resources:
        session.delete(r)
    s.soft_delete(session=session)
    # with session.begin():
    #     for r in s.resources:
    #         session.delete(r)
    #     s.soft_delete(session=session)


@oslo_db_api.wrap_db_retry(max_retries=3, retry_on_deadlock=True,
                           retry_interval=0.5, inc_retry_interval=True)
def stack_lock_create(stack_id, engine_id):
    session = get_session()
    with session.begin():
        lock = session.query(models.StackLock).get(stack_id)
        if lock is not None:
            return lock.engine_id
        session.add(models.StackLock(stack_id=stack_id, engine_id=engine_id))


def stack_lock_get_engine_id(stack_id):
    session = get_session()
    with session.begin():
        lock = session.query(models.StackLock).get(stack_id)
        if lock is not None:
            return lock.engine_id


def persist_state_and_release_lock(context, stack_id, engine_id, values):
    session = _session(context)
    with session.begin():
        rows_updated = (session.query(models.Stack)
                        .filter(models.Stack.id == stack_id)
                        .update(values, synchronize_session=False))
        rows_affected = None
        if rows_updated is not None and rows_updated > 0:
            rows_affected = session.query(
                models.StackLock
            ).filter_by(stack_id=stack_id, engine_id=engine_id).delete()
    session.expire_all()
    if not rows_affected:
        return True


def stack_lock_steal(stack_id, old_engine_id, new_engine_id):
    session = get_session()
    with session.begin():
        lock = session.query(models.StackLock).get(stack_id)
        rows_affected = session.query(
            models.StackLock
        ).filter_by(stack_id=stack_id, engine_id=old_engine_id
                    ).update({"engine_id": new_engine_id})
    if not rows_affected:
        return lock.engine_id if lock is not None else True


def stack_lock_release(stack_id, engine_id):
    session = get_session()
    with session.begin():
        rows_affected = session.query(
            models.StackLock
        ).filter_by(stack_id=stack_id, engine_id=engine_id).delete()
    if not rows_affected:
        return True


def stack_get_root_id(context, stack_id):
    s = stack_get(context, stack_id)
    if not s:
        return None
    while s.owner_id:
        s = stack_get(context, s.owner_id)
    return s.id


def stack_count_total_resources(context, stack_id):
    # count all resources which belong to the root stack
    results = model_query_heat(
        context, models.Resource
    ).filter(models.Resource.root_stack_id == stack_id).count()
    return results


def user_creds_create(context):
    values = context.to_dict()
    user_creds_ref = models.UserCreds()
    if values.get('trust_id'):
        method, trust_id = crypt.encrypt(values.get('trust_id'))
        user_creds_ref.trust_id = trust_id
        user_creds_ref.decrypt_method = method
        user_creds_ref.trustor_user_id = values.get('trustor_user_id')
        user_creds_ref.username = None
        user_creds_ref.password = None
        user_creds_ref.tenant = values.get('tenant')
        user_creds_ref.tenant_id = values.get('tenant_id')
        user_creds_ref.auth_url = values.get('auth_url')
        user_creds_ref.region_name = values.get('region_name')
    else:
        user_creds_ref.update(values)
        method, password = crypt.encrypt(values['password'])
        if len(six.text_type(password)) > 255:
            raise exception.Error(_("Length of OS_PASSWORD after encryption"
                                    " exceeds Heat limit (255 chars)"))
        user_creds_ref.password = password
        user_creds_ref.decrypt_method = method
    user_creds_ref.save(_session(context))
    result = dict(user_creds_ref)

    if values.get('trust_id'):
        result['trust_id'] = values.get('trust_id')
    else:
        result['password'] = values.get('password')

    return result


def user_creds_get(user_creds_id):
    db_result = model_query_heat(None, models.UserCreds).get(user_creds_id)
    if db_result is None:
        return None
    # Return a dict copy of db results, do not decrypt details into db_result
    # or it can be committed back to the DB in decrypted form
    result = dict(db_result)
    del result['decrypt_method']
    result['password'] = crypt.decrypt(
        db_result.decrypt_method, result['password'])
    result['trust_id'] = crypt.decrypt(
        db_result.decrypt_method, result['trust_id'])
    return result


@db_utils.retry_on_stale_data_error
def user_creds_delete(context, user_creds_id):
    session = get_session()
    creds = session.query(models.UserCreds).\
        filter(models.UserCreds.id == user_creds_id).first()
    # creds = model_query_heat(context, models.UserCreds).get(user_creds_id)
    if not creds:
        raise exception.NotFound(
            _('Attempt to delete user creds with id '
              '%(id)s that does not exist') % {'id': user_creds_id})
    creds.delete()
    # session.commit()
    # session = orm_session.Session.object_session(creds)
    # session = get_session()
    # with session.begin(subtransactions=True):
    #     session.delete(creds)


def event_get(context, event_id):
    result = model_query_heat(context, models.Event).get(event_id)
    return result


def event_get_all(context):
    stacks = soft_delete_aware_query(context, models.Stack)
    stack_ids = [stack.id for stack in stacks]
    results = model_query_heat(
        context, models.Event
    ).filter(models.Event.stack_id.in_(stack_ids)).all()
    return results


def event_get_all_by_tenant(context, limit=None, marker=None,
                            sort_keys=None, sort_dir=None, filters=None):
    query = model_query_heat(context, models.Event)
    query = db_filters.exact_filter(query, models.Event, filters)
    query = query.join(
        models.Event.stack
    ).filter_by(tenant=context.tenant_id).filter_by(deleted_at=None)
    filters = None
    return _events_filter_and_page_query(context, query, limit, marker,
                                         sort_keys, sort_dir, filters).all()


def _query_all_by_stack(context, stack_id):
    query = model_query_heat(context, models.Event).filter_by(stack_id=stack_id)
    return query


def event_get_all_by_stack(context, stack_id, limit=None, marker=None,
                           sort_keys=None, sort_dir=None, filters=None):
    query = _query_all_by_stack(context, stack_id)
    return _events_filter_and_page_query(context, query, limit, marker,
                                         sort_keys, sort_dir, filters).all()


def _events_paginate_query(context, query, model, limit=None, sort_keys=None,
                           marker=None, sort_dir=None):
    default_sort_keys = ['created_at']
    if not sort_keys:
        sort_keys = default_sort_keys
        if not sort_dir:
            sort_dir = 'desc'

    # This assures the order of the stacks will always be the same
    # even for sort_key values that are not unique in the database
    sort_keys = sort_keys + ['id']

    model_marker = None
    if marker:
        # not to use model_query(context, model).get(marker), because
        # user can only see the ID(column 'uuid') and the ID as the marker
        model_marker = model_query_heat(
            context, model).filter_by(uuid=marker).first()
    try:
        query = utils.paginate_query(query, model, limit, sort_keys,
                                     model_marker, sort_dir)
    except utils.InvalidSortKey as exc:
        err_msg = encodeutils.exception_to_unicode(exc)
        raise exception.Invalid(reason=err_msg)

    return query


def _events_filter_and_page_query(context, query,
                                  limit=None, marker=None,
                                  sort_keys=None, sort_dir=None,
                                  filters=None):
    if filters is None:
        filters = {}

    sort_key_map = {rpc_api.EVENT_TIMESTAMP: models.Event.created_at.key,
                    rpc_api.EVENT_RES_TYPE: models.Event.resource_type.key}
    whitelisted_sort_keys = _get_sort_keys(sort_keys, sort_key_map)

    query = db_filters.exact_filter(query, models.Event, filters)

    return _events_paginate_query(context, query, models.Event, limit,
                                  whitelisted_sort_keys, marker, sort_dir)


def event_count_all_by_stack(context, stack_id):
    # query = model_query_heat_original(context, func.count(models.Event.id))
    session = get_session()
    session.begin(subtransactions=True)
    query = session.query(func.count(models.Event.id))
    session.commit()
    # return query
    return query.filter_by(stack_id=stack_id).scalar()


def _delete_event_rows(context, stack_id, limit):
    # MySQL does not support LIMIT in subqueries,
    # sqlite does not support JOIN in DELETE.
    # So we must manually supply the IN() values.
    # pgsql SHOULD work with the pure DELETE/JOIN below but that must be
    # confirmed via integration tests.
    query = _query_all_by_stack(context, stack_id)
    session = _session(context)
    ids = [r.id for r in query.order_by(
        models.Event.id).limit(limit).all()]
    q = session.query(models.Event).filter(
        models.Event.id.in_(ids))
    return q.delete(synchronize_session='fetch')


def event_create(context, values):
    if 'stack_id' in values and cfg.CONF.max_events_per_stack:
        if ((event_count_all_by_stack(context, values['stack_id']) >=
             cfg.CONF.max_events_per_stack)):
            # prune
            _delete_event_rows(
                context, values['stack_id'], cfg.CONF.event_purge_batch_size)
    event_ref = models.Event()
    event_ref.update(values)
    # session = _session(context)
    session = get_session()
    session.begin(subtransactions=True)
    event_ref.save(session)
    session.commit()
    return event_ref


def watch_rule_get(context, watch_rule_id):
    result = model_query_heat(context, models.WatchRule).get(watch_rule_id)
    return result


def watch_rule_get_by_name(context, watch_rule_name):
    result = model_query_heat(
        context, models.WatchRule).filter_by(name=watch_rule_name).first()
    return result


def watch_rule_get_all(context):
    results = model_query_heat(context, models.WatchRule).all()
    return results


def watch_rule_get_all_by_stack(context, stack_id):
    results = model_query_heat(
        context, models.WatchRule).filter_by(stack_id=stack_id).all()
    return results


def watch_rule_create(context, values):
    obj_ref = models.WatchRule()
    obj_ref.update(values)
    obj_ref.save(_session(context))
    return obj_ref


def watch_rule_update(context, watch_id, values):
    wr = watch_rule_get(context, watch_id)

    if not wr:
        raise exception.NotFound(_('Attempt to update a watch with id: '
                                 '%(id)s %(msg)s') % {
                                     'id': watch_id,
                                     'msg': 'that does not exist'})
    wr.update(values)
    wr.save(_session(context))


def watch_rule_delete(context, watch_id):
    wr = watch_rule_get(context, watch_id)
    if not wr:
        raise exception.NotFound(_('Attempt to delete watch_rule: '
                                 '%(id)s %(msg)s') % {
                                     'id': watch_id,
                                     'msg': 'that does not exist'})
    session = orm_session.Session.object_session(wr)
    with session.begin():
        for d in wr.watch_data:
            session.delete(d)
        session.delete(wr)


def watch_data_create(context, values):
    obj_ref = models.WatchData()
    obj_ref.update(values)
    obj_ref.save(_session(context))
    return obj_ref


def watch_data_get_all(context):
    results = model_query_heat(context, models.WatchData).all()
    return results


def watch_data_get_all_by_watch_rule_id(context, watch_rule_id):
    results = model_query_heat(context, models.WatchData).filter_by(
        watch_rule_id=watch_rule_id).all()
    return results


def software_config_create(context, values):
    obj_ref = models.SoftwareConfig()
    obj_ref.update(values)
    obj_ref.save(_session(context))
    return obj_ref


def software_config_get(context, config_id):
    result = model_query_heat(context, models.SoftwareConfig).get(config_id)
    if (result is not None and context is not None and
            result.tenant != context.tenant_id):
        result = None

    if not result:
        raise exception.NotFound(_('Software config with id %s not found') %
                                 config_id)
    return result


def software_config_get_all(context, limit=None, marker=None,
                            tenant_safe=True):
    query = model_query_heat(context, models.SoftwareConfig)
    if tenant_safe:
        query = query.filter_by(tenant=context.tenant_id)
    return _paginate_query(context, query, models.SoftwareConfig,
                           limit=limit, marker=marker).all()


def software_config_delete(context, config_id):
    config = software_config_get(context, config_id)
    # Query if the software config has been referenced by deployment.
    result = model_query_heat(context, models.SoftwareDeployment).filter_by(
        config_id=config_id).first()
    if result:
        msg = (_("Software config with id %s can not be deleted as "
                 "it is referenced.") % config_id)
        raise exception.InvalidRestrictedAction(message=msg)
    session = orm_session.Session.object_session(config)
    with session.begin():
        session.delete(config)


def software_deployment_create(context, values):
    obj_ref = models.SoftwareDeployment()
    obj_ref.update(values)
    session = _session(context)
    session.begin()
    obj_ref.save(session)
    session.commit()
    return obj_ref


def software_deployment_get(context, deployment_id):
    result = model_query_heat(context, models.SoftwareDeployment).get(deployment_id)
    if (result is not None and context is not None and
        context.tenant_id not in (result.tenant,
                                  result.stack_user_project_id)):
        result = None

    if not result:
        raise exception.NotFound(_('Deployment with id %s not found') %
                                 deployment_id)
    return result


def software_deployment_get_all(context, server_id=None):
    sd = models.SoftwareDeployment
    query = model_query_heat(
        context, sd
    ).filter(sqlalchemy.or_(
             sd.tenant == context.tenant_id,
             sd.stack_user_project_id == context.tenant_id)
             ).order_by(sd.created_at)
    if server_id:
        query = query.filter_by(server_id=server_id)
    return query.all()


def software_deployment_update(context, deployment_id, values):
    deployment = software_deployment_get(context, deployment_id)
    deployment.update_and_save(values)
    return deployment


def software_deployment_delete(context, deployment_id):
    deployment = software_deployment_get(context, deployment_id)
    deployment.delete()


def snapshot_create(context, values):
    obj_ref = models.Snapshot()
    obj_ref.update(values)
    obj_ref.save(_session(context))
    return obj_ref


def snapshot_get(context, snapshot_id):
    result = model_query_heat(context, models.Snapshot).get(snapshot_id)
    if (result is not None and context is not None and
            context.tenant_id != result.tenant):
        result = None

    if not result:
        raise exception.NotFound(_('Snapshot with id %s not found') %
                                 snapshot_id)
    return result


def snapshot_get_by_stack(context, snapshot_id, stack):
    snapshot = snapshot_get(context, snapshot_id)
    if snapshot.stack_id != stack.id:
        raise exception.SnapshotNotFound(snapshot=snapshot_id,
                                         stack=stack.name)

    return snapshot


def snapshot_update(context, snapshot_id, values):
    snapshot = snapshot_get(context, snapshot_id)
    snapshot.update(values)
    snapshot.save(_session(context))
    return snapshot


def snapshot_delete(context, snapshot_id):
    snapshot = snapshot_get(context, snapshot_id)
    session = orm_session.Session.object_session(snapshot)
    with session.begin():
        session.delete(snapshot)


def snapshot_get_all(context, stack_id):
    return model_query_heat(context, models.Snapshot).filter_by(
        stack_id=stack_id, tenant=context.tenant_id)


def service_create(context, values):
    service = models.Service()
    service.update(values)
    service.save(_session(context))
    return service


def service_update(context, service_id, values):
    service = service_get(context, service_id)
    values.update({'updated_at': timeutils.utcnow()})
    service.update(values)
    service.save(_session(context))
    return service


def service_delete(context, service_id, soft_delete=True):
    service = service_get(context, service_id)
    session = orm_session.Session.object_session(service)
    with session.begin():
        if soft_delete:
            service.soft_delete(session=session)
        else:
            session.delete(service)


def service_get(context, service_id):
    result = model_query_heat(context, models.Service).get(service_id)
    if result is None:
        raise exception.EntityNotFound(entity='Service', name=service_id)
    return result


def service_get_all(context):
    return (model_query_heat(context, models.Service).
            filter_by(deleted_at=None).all())


def service_get_all_by_args(context, host, binary, hostname):
    return (model_query_heat(context, models.Service).
            filter_by(host=host).
            filter_by(binary=binary).
            filter_by(hostname=hostname).all())


def purge_deleted(age, granularity='days'):
    try:
        age = int(age)
    except ValueError:
        raise exception.Error(_("age should be an integer"))
    if age < 0:
        raise exception.Error(_("age should be a positive integer"))

    if granularity not in ('days', 'hours', 'minutes', 'seconds'):
        raise exception.Error(
            _("granularity should be days, hours, minutes, or seconds"))

    if granularity == 'days':
        age = age * 86400
    elif granularity == 'hours':
        age = age * 3600
    elif granularity == 'minutes':
        age = age * 60

    time_line = timeutils.utcnow() - datetime.timedelta(seconds=age)
    engine = get_engine()
    meta = sqlalchemy.MetaData()
    meta.bind = engine

    stack = sqlalchemy.Table('stack', meta, autoload=True)
    stack_lock = sqlalchemy.Table('stack_lock', meta, autoload=True)
    stack_tag = sqlalchemy.Table('stack_tag', meta, autoload=True)
    resource = sqlalchemy.Table('resource', meta, autoload=True)
    resource_data = sqlalchemy.Table('resource_data', meta, autoload=True)
    event = sqlalchemy.Table('event', meta, autoload=True)
    raw_template = sqlalchemy.Table('raw_template', meta, autoload=True)
    user_creds = sqlalchemy.Table('user_creds', meta, autoload=True)
    service = sqlalchemy.Table('service', meta, autoload=True)
    syncpoint = sqlalchemy.Table('sync_point', meta, autoload=True)

    # find the soft-deleted stacks that are past their expiry
    stack_where = sqlalchemy.select([stack.c.id, stack.c.raw_template_id,
                                     stack.c.prev_raw_template_id,
                                     stack.c.user_creds_id]).where(
                                         stack.c.deleted_at < time_line)
    stacks = list(engine.execute(stack_where))
    if stacks:
        stack_ids = [i[0] for i in stacks]
        # delete stack locks (just in case some got stuck)
        stack_lock_del = stack_lock.delete().where(
            stack_lock.c.stack_id.in_(stack_ids))
        engine.execute(stack_lock_del)
        # delete stack tags
        stack_tag_del = stack_tag.delete().where(
            stack_tag.c.stack_id.in_(stack_ids))
        engine.execute(stack_tag_del)
        # delete resource_data
        res_where = sqlalchemy.select([resource.c.id]).where(
            resource.c.stack_id.in_(stack_ids))
        res_data_del = resource_data.delete().where(
            resource_data.c.resource_id.in_(res_where))
        engine.execute(res_data_del)
        # delete resources
        res_del = resource.delete().where(resource.c.stack_id.in_(stack_ids))
        engine.execute(res_del)
        # delete events
        event_del = event.delete().where(event.c.stack_id.in_(stack_ids))
        engine.execute(event_del)
        # clean up any sync_points that may have lingered
        sync_del = syncpoint.delete().where(
            syncpoint.c.stack_id.in_(stack_ids))
        engine.execute(sync_del)
        # delete the stacks
        stack_del = stack.delete().where(stack.c.id.in_(stack_ids))
        engine.execute(stack_del)
        # delete orphaned raw templates
        raw_template_ids = [i[1] for i in stacks if i[1] is not None]
        raw_template_ids.extend(i[2] for i in stacks if i[2] is not None)
        if raw_template_ids:
            # keep those still referenced
            raw_tmpl_sel = sqlalchemy.select([stack.c.raw_template_id]).where(
                stack.c.raw_template_id.in_(raw_template_ids))
            raw_tmpl = [i[0] for i in engine.execute(raw_tmpl_sel)]
            raw_template_ids = set(raw_template_ids) - set(raw_tmpl)
            raw_tmpl_sel = sqlalchemy.select(
                [stack.c.prev_raw_template_id]).where(
                stack.c.prev_raw_template_id.in_(raw_template_ids))
            raw_tmpl = [i[0] for i in engine.execute(raw_tmpl_sel)]
            raw_template_ids = raw_template_ids - set(raw_tmpl)
            raw_templ_del = raw_template.delete().where(
                raw_template.c.id.in_(raw_template_ids))
            engine.execute(raw_templ_del)
        # purge any user creds that are no longer referenced
        user_creds_ids = [i[3] for i in stacks if i[3] is not None]
        if user_creds_ids:
            # keep those still referenced
            user_sel = sqlalchemy.select([stack.c.user_creds_id]).where(
                stack.c.user_creds_id.in_(user_creds_ids))
            users = [i[0] for i in engine.execute(user_sel)]
            user_creds_ids = set(user_creds_ids) - set(users)
            usr_creds_del = user_creds.delete().where(
                user_creds.c.id.in_(user_creds_ids))
            engine.execute(usr_creds_del)
    # Purge deleted services
    srvc_del = service.delete().where(service.c.deleted_at < time_line)
    engine.execute(srvc_del)


def sync_point_delete_all_by_stack_and_traversal(context, stack_id,
                                                 traversal_id):
    rows_deleted = model_query_heat(context, models.SyncPoint).filter_by(
        stack_id=stack_id, traversal_id=traversal_id).delete()
    return rows_deleted


@oslo_db_api.wrap_db_retry(max_retries=3, retry_on_deadlock=True,
                           retry_interval=0.5, inc_retry_interval=True)
def sync_point_create(context, values):
    values['entity_id'] = str(values['entity_id'])
    sync_point_ref = models.SyncPoint()
    sync_point_ref.update(values)
    sync_point_ref.save(_session(context))
    return sync_point_ref


def sync_point_get(context, entity_id, traversal_id, is_update):
    entity_id = str(entity_id)
    return model_query_heat(context, models.SyncPoint).get(
        (entity_id, traversal_id, is_update)
    )


def sync_point_update_input_data(context, entity_id,
                                 traversal_id, is_update, atomic_key,
                                 input_data):
    entity_id = str(entity_id)
    rows_updated = model_query_heat(context, models.SyncPoint).filter_by(
        entity_id=entity_id,
        traversal_id=traversal_id,
        is_update=is_update,
        atomic_key=atomic_key
    ).update({"input_data": input_data, "atomic_key": atomic_key + 1})
    return rows_updated


def db_sync(engine, version=None):
    """Migrate the database to `version` or the most recent version."""

    return migration.db_sync(engine, version=version)


def db_version(engine):
    """Display the current database version."""
    return migration.db_version(engine)


def db_encrypt_parameters_and_properties(ctxt, encryption_key, batch_size=50):
    """Encrypt parameters and properties for all templates in db.

    :param ctxt: RPC context
    :param encryption_key: key that will be used for parameter and property
                           encryption
    :param batch_size: number of templates requested from db in each iteration.
                       50 means that heat requests 50 templates, encrypt them
                       and proceed with next 50 items.
    :return: list of exceptions encountered during encryption
    """
    from conveyor.conveyorheat.engine import template
    session = get_session()
    with session.begin():
        query = session.query(models.RawTemplate)
        excs = []
        for raw_template in _get_batch(
                session=session, ctxt=ctxt, query=query,
                model=models.RawTemplate, batch_size=batch_size):
            try:
                tmpl = template.Template.load(
                    ctxt, raw_template.id, raw_template)
                param_schemata = tmpl.param_schemata()
                env = raw_template.environment

                if (not env or
                        'parameters' not in env or
                        not tmpl.param_schemata()):
                    continue
                if 'encrypted_param_names' in env:
                    encrypted_params = env['encrypted_param_names']
                else:
                    encrypted_params = []

                for param_name, param_val in env['parameters'].items():
                    if ((param_name in encrypted_params) or
                       (not param_schemata[param_name].hidden)):
                            continue
                    encrypted_val = crypt.encrypt(six.text_type(param_val),
                                                  encryption_key)
                    env['parameters'][param_name] = encrypted_val
                    encrypted_params.append(param_name)

                if encrypted_params:
                    environment = env.copy()
                    environment['encrypted_param_names'] = encrypted_params
                    raw_template_update(ctxt, raw_template.id,
                                        {'environment': environment})
            except Exception as exc:
                LOG.exception(_LE('Failed to encrypt parameters of raw '
                                  'template %(id)d'), {'id': raw_template.id})
                excs.append(exc)
                continue

        query = session.query(models.Resource).filter(
            ~models.Resource.properties_data.is_(None),
            ~models.Resource.properties_data_encrypted.is_(True))
        for resource in _get_batch(
                session=session, ctxt=ctxt, query=query, model=models.Resource,
                batch_size=batch_size):
            try:
                result = {}
                if not resource.properties_data:
                    continue
                for prop_name, prop_value in resource.properties_data.items():
                    prop_string = jsonutils.dumps(prop_value)
                    encrypted_value = crypt.encrypt(prop_string,
                                                    encryption_key)
                    result[prop_name] = encrypted_value
                resource.properties_data = result
                resource.properties_data_encrypted = True
                resource_update(ctxt, resource.id,
                                {'properties_data': result,
                                 'properties_data_encrypted': True},
                                resource.atomic_key)
            except Exception as exc:
                LOG.exception(_LE('Failed to encrypt properties_data of '
                                  'resource %(id)d'), {'id': resource.id})
                excs.append(exc)
                continue
        return excs


def db_decrypt_parameters_and_properties(ctxt, encryption_key, batch_size=50):
    """Decrypt parameters and properties for all templates in db.

    :param ctxt: RPC context
    :param encryption_key: key that will be used for parameter and property
                           decryption
    :param batch_size: number of templates requested from db in each iteration.
                       50 means that heat requests 50 templates, encrypt them
                       and proceed with next 50 items.
    :return: list of exceptions encountered during decryption
    """
    session = get_session()
    excs = []
    with session.begin():
        query = session.query(models.RawTemplate)
        for raw_template in _get_batch(
                session=session, ctxt=ctxt, query=query,
                model=models.RawTemplate, batch_size=batch_size):
            try:
                parameters = raw_template.environment['parameters']
                encrypted_params = raw_template.environment[
                    'encrypted_param_names']
                for param_name in encrypted_params:
                    method, value = parameters[param_name]
                    decrypted_val = crypt.decrypt(method, value,
                                                  encryption_key)
                    parameters[param_name] = decrypted_val

                environment = raw_template.environment.copy()
                environment['encrypted_param_names'] = []
                raw_template_update(ctxt, raw_template.id,
                                    {'environment': environment})
            except Exception as exc:
                LOG.exception(_LE('Failed to decrypt parameters of raw '
                                  'template %(id)d'), {'id': raw_template.id})
                excs.append(exc)
                continue

        query = session.query(models.Resource).filter(
            ~models.Resource.properties_data.is_(None),
            models.Resource.properties_data_encrypted.is_(True))
        for resource in _get_batch(
                session=session, ctxt=ctxt, query=query, model=models.Resource,
                batch_size=batch_size):
            try:
                result = {}
                for prop_name, prop_value in resource.properties_data.items():
                    method, value = prop_value
                    decrypted_value = crypt.decrypt(method, value,
                                                    encryption_key)
                    prop_string = jsonutils.loads(decrypted_value)
                    result[prop_name] = prop_string
                resource.properties_data = result
                resource.properties_data_encrypted = False
                resource_update(ctxt, resource.id,
                                {'properties_data': result,
                                 'properties_data_encrypted': False},
                                resource.atomic_key)
            except Exception as exc:
                LOG.exception(_LE('Failed to decrypt properties_data of '
                                  'resource %(id)d'), {'id': resource.id})
                excs.append(exc)
                continue
        return excs


def _get_batch(session, ctxt, query, model, batch_size=50):
    last_batch_marker = None
    while True:
        results = _paginate_query(
            context=ctxt, query=query, model=model, limit=batch_size,
            marker=last_batch_marker).all()
        if not results:
            break
        else:
            for result in results:
                yield result
            last_batch_marker = results[-1].id


def reset_stack_status(context, stack_id, stack=None):
    if stack is None:
        stack = model_query_heat(context, models.Stack).get(stack_id)

    if stack is None:
        raise exception.NotFound(_('Stack with id %s not found') % stack_id)

    session = _session(context)
    with session.begin():
        query = model_query_heat(context, models.Resource).filter_by(
            status='IN_PROGRESS', stack_id=stack_id)
        query.update({'status': 'FAILED',
                      'status_reason': 'Stack status manually reset',
                      'engine_id': None})

        query = model_query_heat(context, models.ResourceData)
        query = query.join(models.Resource)
        query = query.filter_by(stack_id=stack_id)
        query = query.filter(
            models.ResourceData.key.in_(heat_environment.HOOK_TYPES))
        data_ids = [data.id for data in query]

        if data_ids:
            query = model_query_heat(context, models.ResourceData)
            query = query.filter(models.ResourceData.id.in_(data_ids))
            query.delete(synchronize_session='fetch')

    query = model_query_heat(context, models.Stack).filter_by(owner_id=stack_id)
    for child in query:
        reset_stack_status(context, child.id, child)

    with session.begin():
        if stack.status == 'IN_PROGRESS':
            stack.status = 'FAILED'
            stack.status_reason = 'Stack status manually reset'

        session.query(
            models.StackLock
        ).filter_by(stack_id=stack_id).delete()


def gw_alarm_create(context, values):
    obj_ref = models.GWAlarm()
    obj_ref.update(values)
    session = _session(context)
    with session.begin():
        obj_ref.save(session)
    return obj_ref


def gw_alarm_get(context, alarm_id):
    result = model_query_heat(context, models.GWAlarm).get(alarm_id)

    if not result:
        raise exception.NotFound(_('Alarm with id %s not found') %
                                 alarm_id)
    return result


def gw_alarm_update(context, alarm_id, values):
    alarm = gw_alarm_get(context, alarm_id)
    alarm.update(values)
    session = _session(context)
    with session.begin():
        alarm.save(session)
    return alarm


def gw_alarm_delete(context, alarm_id):
    alarm = gw_alarm_get(context, alarm_id)
    session = orm_session.object_session(alarm)
    with session.begin():
        session.delete(alarm)


def gw_alarm_get_all(context, tenant_safe):
    query = model_query_heat(context, models.GWAlarm)

    if tenant_safe:
        ret = query.filter_by(tenant=context.tenant_id)
    else:
        ret = query.all()
    return ret


def gw_alarm_get_all_by_group(context, group_id):
    query = model_query_heat(context, models.GWAlarm).filter_by(
        group_id=group_id)

    return query.all()


def gw_group_create(context, values):
    group_ref = models.GWGroup()
    group_ref.update(values)
    session = _session(context)
    with session.begin():
        group_ref.save(session)
    return group_ref


def gw_group_delete(context, group_id):
    # first we need delete member in current group
    gw_member_delete_by_group_id(context, group_id)
    group = gw_group_get(context, group_id)
    if not group:
        raise exception.NotFound(_('Attempt to delete a group with id: '
                                   '%(id)s %(msg)s') % {
                                       'id': group_id,
                                       'msg': 'that does not exist'})
    session = orm_session.object_session(group)
    with session.begin():
        session.delete(group)


def gw_group_get(context, group_id):
    result = model_query_heat(context, models.GWGroup).get(group_id)
    if not result:
        raise exception.NotFound(_('Group with id %s not found') %
                                 group_id)
    return result


def gw_group_get_all(context, tenant_safe=False):
    query = model_query_heat(context, models.GWGroup)

    if tenant_safe:
        ret = query.filter_by(tenant=context.tenant_id)
    else:
        ret = query.all()
    return ret


def gw_group_update(context, group_id, values):
    group = gw_group_get(context, group_id)
    group.update(values)
    session = _session(context)
    with session.begin():
        group.save(session)
    return group


def gw_member_get_all_by_group(context, group_id):
    query = model_query_heat(context, models.GWMember).filter_by(group_id=group_id)

    return query.all()


def gw_member_create(context, values):
    member_ref = models.GWMember()
    member_ref.update(values)
    session = _session(context)
    with session.begin():
        member_ref.save(session)
    return member_ref


def gw_member_batch_insert(context, members):
    session = _session(context)
    session.begin()
    try:
        for member in members:
            member_ref = models.GWMember()
            member_ref.update(member)

        session.commit()
    except Exception:
        session.roolback()


def gw_member_delete(context, member_id):
    member = gw_member_get(context, member_id)
    if not member:
        raise exception.NotFound(_('Attempt to delete a member with id: '
                                   '%(id)s %(msg)s') % {
                                       'id': member_id,
                                       'msg': 'that does not exist'})

    session = orm_session.object_session(member)
    with session.begin():
        session.delete(member)


def gw_member_delete_by_group_id(context, group_id):
    session = _session(context)
    q = session.query(models.GWMember).filter(
        models.GWMember.group_id.in_([group_id]))
    return q.delete(synchronize_session='fetch')


def gw_member_get(context, member_id):
    result = model_query_heat(context, models.GWmember).get(member_id)
    if (result is not None and context is not None and
            context.tenant_id != result.tenant):
        result = None

    if not result:
        raise exception.NotFound(_('Member with id %s not found') %
                                 member_id)
    return result


PAGINATION_HELPERS = {
    models.Plan: (_plan_get_query, _process_plan_filters, _plan_get),
}
