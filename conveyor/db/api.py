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

"""Defines interface for DB access.

Functions in this module are imported into the conveyor.db namespace. Call
these functions from conveyor.db namespace, not the conveyor.db.api namespace.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.

"""

from oslo_config import cfg
from oslo_db import api
from oslo_log import log as logging

db_opts = [
]

CONF = cfg.CONF
CONF.register_opts(db_opts)

_BACKEND_MAPPING = {'sqlalchemy': 'conveyor.db.sqlalchemy.api'}

# IMPL = concurrency.TpoolDbapiWrapper(CONF, backend_mapping=_BACKEND_MAPPING)
IMPL = api.DBAPI.from_config(CONF, backend_mapping=_BACKEND_MAPPING)

LOG = logging.getLogger(__name__)

# The maximum value a signed INT type may have
MAX_INT = 0x7FFFFFFF


def plan_get(context, id):
    return IMPL.plan_get(context, id)


def plan_create(context, values):
    """Create a plan from the values dictionary."""
    return IMPL.plan_create(context, values)


def plan_delete(context, id):
    """Destroy the plan or raise if it does not exist."""
    return IMPL.plan_delete(context, id)


def plan_update(context, id, values):
    return IMPL.plan_update(context, id, values)


def plan_get_all(context, marker=None, limit=None, sort_keys=None,
                 sort_dirs=None, filters=None):
    """get all plans."""
    return IMPL.plan_get_all(context, marker=marker, limit=limit,
                             sort_keys=sort_keys, sort_dirs=sort_dirs,
                             filters=filters)


def plan_stack_create(context, values):
    return IMPL.plan_stack_create(context, values)


def plan_stack_get(context, plan_id, read_deleted='no'):
    return IMPL.plan_stack_get(context, plan_id, read_deleted=read_deleted)


def plan_stack_delete(context, plan_id, stack_id):
    return IMPL.plan_stack_delete(context, plan_id, stack_id)


def plan_stack_delete_all(context, plan_id):
    return IMPL.plan_stack_delete_all(context, plan_id)


def plan_stack_update(context, plan_id, stack_id, values):
    return IMPL.plan_stack_update(context, plan_id, stack_id, values)


# add from heat
def get_engine():
    return IMPL.get_engine()


def get_session():
    return IMPL.get_session()


def raw_template_get(context, template_id):
    return IMPL.raw_template_get(context, template_id)


def raw_template_create(context, values):
    return IMPL.raw_template_create(context, values)


def raw_template_update(context, template_id, values):
    return IMPL.raw_template_update(context, template_id, values)


def raw_template_delete(context, template_id):
    return IMPL.raw_template_delete(context, template_id)


def resource_data_get_all(context, resource_id, data=None):
    return IMPL.resource_data_get_all(context, resource_id, data)


def resource_data_get(resource, key):
    return IMPL.resource_data_get(resource, key)


def resource_data_set(resource, key, value, redact=False):
    return IMPL.resource_data_set(resource, key, value, redact=redact)


def resource_data_get_by_key(context, resource_id, key):
    return IMPL.resource_data_get_by_key(context, resource_id, key)


def resource_data_delete(resource, key):
    """Remove a resource_data element associated to a resource."""
    return IMPL.resource_data_delete(resource, key)


def stack_tags_set(context, stack_id, tags):
    return IMPL.stack_tags_set(context, stack_id, tags)


def stack_tags_delete(context, stack_id):
    return IMPL.stack_tags_delete(context, stack_id)


def stack_tags_get(context, stack_id):
    return IMPL.stack_tags_get(context, stack_id)


def resource_get(context, resource_id):
    return IMPL.resource_get(context, resource_id)


def resource_get_all(context):
    return IMPL.resource_get_all(context)


def resource_update(context, resource_id, values, atomic_key,
                    expected_engine_id=None):
    return IMPL.resource_update(context, resource_id, values, atomic_key,
                                expected_engine_id)


def resource_create(context, values):
    return IMPL.resource_create(context, values)


def resource_exchange_stacks(context, resource_id1, resource_id2):
    return IMPL.resource_exchange_stacks(context, resource_id1, resource_id2)


def resource_get_all_by_stack(context, stack_id, key_id=False, filters=None):
    return IMPL.resource_get_all_by_stack(context, stack_id, key_id, filters)


def resource_get_by_name_and_stack(context, resource_name, stack_id):
    return IMPL.resource_get_by_name_and_stack(context,
                                               resource_name, stack_id)


def resource_get_by_physical_resource_id(context, physical_resource_id):
    return IMPL.resource_get_by_physical_resource_id(context,
                                                     physical_resource_id)


def stack_get(context, stack_id, show_deleted=False, tenant_safe=True,
              eager_load=False):
    return IMPL.stack_get(context, stack_id, show_deleted=show_deleted,
                          tenant_safe=tenant_safe,
                          eager_load=eager_load)


def stack_get_status(context, stack_id):
    return IMPL.stack_get_status(context, stack_id)


def stack_get_by_name_and_owner_id(context, stack_name, owner_id):
    return IMPL.stack_get_by_name_and_owner_id(context, stack_name,
                                               owner_id=owner_id)


def stack_get_by_name(context, stack_name):
    return IMPL.stack_get_by_name(context, stack_name)


def stack_get_all(context, limit=None, sort_keys=None, marker=None,
                  sort_dir=None, filters=None, tenant_safe=True,
                  show_deleted=False, show_nested=False, show_hidden=False,
                  tags=None, tags_any=None, not_tags=None,
                  not_tags_any=None):
    return IMPL.stack_get_all(context, limit, sort_keys,
                              marker, sort_dir, filters, tenant_safe,
                              show_deleted, show_nested, show_hidden,
                              tags, tags_any, not_tags, not_tags_any)


def stack_get_all_by_owner_id(context, owner_id):
    return IMPL.stack_get_all_by_owner_id(context, owner_id)


def stack_count_all(context, filters=None, tenant_safe=True,
                    show_deleted=False, show_nested=False, show_hidden=False,
                    tags=None, tags_any=None, not_tags=None,
                    not_tags_any=None):
    return IMPL.stack_count_all(context, filters=filters,
                                tenant_safe=tenant_safe,
                                show_deleted=show_deleted,
                                show_nested=show_nested,
                                show_hidden=show_hidden,
                                tags=tags,
                                tags_any=tags_any,
                                not_tags=not_tags,
                                not_tags_any=not_tags_any)


def stack_create(context, values):
    return IMPL.stack_create(context, values)


def stack_update(context, stack_id, values, exp_trvsl=None):
    return IMPL.stack_update(context, stack_id, values, exp_trvsl=exp_trvsl)


def stack_delete(context, stack_id):
    return IMPL.stack_delete(context, stack_id)


def stack_lock_create(stack_id, engine_id):
    return IMPL.stack_lock_create(stack_id, engine_id)


def stack_lock_get_engine_id(stack_id):
    return IMPL.stack_lock_get_engine_id(stack_id)


def stack_lock_steal(stack_id, old_engine_id, new_engine_id):
    return IMPL.stack_lock_steal(stack_id, old_engine_id, new_engine_id)


def stack_lock_release(stack_id, engine_id):
    return IMPL.stack_lock_release(stack_id, engine_id)


def persist_state_and_release_lock(context, stack_id, engine_id, values):
    return IMPL.persist_state_and_release_lock(context, stack_id,
                                               engine_id, values)


def stack_get_root_id(context, stack_id):
    return IMPL.stack_get_root_id(context, stack_id)


def stack_count_total_resources(context, stack_id):
    return IMPL.stack_count_total_resources(context, stack_id)


def user_creds_create(context):
    return IMPL.user_creds_create(context)


def user_creds_delete(context, user_creds_id):
    return IMPL.user_creds_delete(context, user_creds_id)


def user_creds_get(context_id):
    return IMPL.user_creds_get(context_id)


def event_get(context, event_id):
    return IMPL.event_get(context, event_id)


def event_get_all(context):
    return IMPL.event_get_all(context)


def event_get_all_by_tenant(context, limit=None, marker=None,
                            sort_keys=None, sort_dir=None, filters=None):
    return IMPL.event_get_all_by_tenant(context,
                                        limit=limit,
                                        marker=marker,
                                        sort_keys=sort_keys,
                                        sort_dir=sort_dir,
                                        filters=filters)


def event_get_all_by_stack(context, stack_id, limit=None, marker=None,
                           sort_keys=None, sort_dir=None, filters=None):
    return IMPL.event_get_all_by_stack(context, stack_id,
                                       limit=limit,
                                       marker=marker,
                                       sort_keys=sort_keys,
                                       sort_dir=sort_dir,
                                       filters=filters)


def event_count_all_by_stack(context, stack_id):
    return IMPL.event_count_all_by_stack(context, stack_id)


def event_create(context, values):
    return IMPL.event_create(context, values)


def watch_rule_get(context, watch_rule_id):
    return IMPL.watch_rule_get(context, watch_rule_id)


def watch_rule_get_by_name(context, watch_rule_name):
    return IMPL.watch_rule_get_by_name(context, watch_rule_name)


def watch_rule_get_all(context):
    return IMPL.watch_rule_get_all(context)


def watch_rule_get_all_by_stack(context, stack_id):
    return IMPL.watch_rule_get_all_by_stack(context, stack_id)


def watch_rule_create(context, values):
    return IMPL.watch_rule_create(context, values)


def watch_rule_update(context, watch_id, values):
    return IMPL.watch_rule_update(context, watch_id, values)


def watch_rule_delete(context, watch_id):
    return IMPL.watch_rule_delete(context, watch_id)


def watch_data_create(context, values):
    return IMPL.watch_data_create(context, values)


def watch_data_get_all(context):
    return IMPL.watch_data_get_all(context)


def watch_data_get_all_by_watch_rule_id(context, watch_rule_id):
    return IMPL.watch_data_get_all_by_watch_rule_id(context, watch_rule_id)


def software_config_create(context, values):
    return IMPL.software_config_create(context, values)


def software_config_get(context, config_id):
    return IMPL.software_config_get(context, config_id)


def software_config_get_all(context, limit=None, marker=None,
                            tenant_safe=True):
    return IMPL.software_config_get_all(context,
                                        limit=limit,
                                        marker=marker,
                                        tenant_safe=tenant_safe)


def software_config_delete(context, config_id):
    return IMPL.software_config_delete(context, config_id)


def software_deployment_create(context, values):
    return IMPL.software_deployment_create(context, values)


def software_deployment_get(context, deployment_id):
    return IMPL.software_deployment_get(context, deployment_id)


def software_deployment_get_all(context, server_id=None):
    return IMPL.software_deployment_get_all(context, server_id)


def software_deployment_update(context, deployment_id, values):
    return IMPL.software_deployment_update(context, deployment_id, values)


def software_deployment_delete(context, deployment_id):
    return IMPL.software_deployment_delete(context, deployment_id)


def snapshot_create(context, values):
    return IMPL.snapshot_create(context, values)


def snapshot_get(context, snapshot_id):
    return IMPL.snapshot_get(context, snapshot_id)


def snapshot_get_by_stack(context, snapshot_id, stack):
    return IMPL.snapshot_get_by_stack(context, snapshot_id, stack)


def snapshot_update(context, snapshot_id, values):
    return IMPL.snapshot_update(context, snapshot_id, values)


def snapshot_delete(context, snapshot_id):
    return IMPL.snapshot_delete(context, snapshot_id)


def snapshot_get_all(context, stack_id):
    return IMPL.snapshot_get_all(context, stack_id)


def service_create(context, values):
    return IMPL.service_create(context, values)


def service_update(context, service_id, values):
    return IMPL.service_update(context, service_id, values)


def service_delete(context, service_id, soft_delete=True):
    return IMPL.service_delete(context, service_id, soft_delete)


def service_get(context, service_id):
    return IMPL.service_get(context, service_id)


def service_get_all(context):
    return IMPL.service_get_all(context)


def service_get_all_by_args(context, host, binary, hostname):
    return IMPL.service_get_all_by_args(context, host, binary, hostname)


def sync_point_delete_all_by_stack_and_traversal(context, stack_id,
                                                 traversal_id):
    return IMPL.sync_point_delete_all_by_stack_and_traversal(context,
                                                             stack_id,
                                                             traversal_id)


def sync_point_create(context, values):
    return IMPL.sync_point_create(context, values)


def sync_point_get(context, entity_id, traversal_id, is_update):
    return IMPL.sync_point_get(context, entity_id, traversal_id, is_update)


def sync_point_update_input_data(context, entity_id,
                                 traversal_id, is_update, atomic_key,
                                 input_data):
    return IMPL.sync_point_update_input_data(context, entity_id,
                                             traversal_id, is_update,
                                             atomic_key, input_data)


def db_sync(engine, version=None):
    """Migrate the database to `version` or the most recent version."""
    return IMPL.db_sync(engine, version=version)


def db_version(engine):
    """Display the current database version."""
    return IMPL.db_version(engine)


def gw_alarm_create(context, values):
    return IMPL.gw_alarm_create(context, values)


def gw_alarm_get(context, alarm_id, show_deleted=False):
    return IMPL.gw_alarm_get(context, alarm_id)


def gw_alarm_update(context, alarm_id, values):
    return IMPL.gw_alarm_update(context, alarm_id, values)


def gw_alarm_delete(context, alarm_id):
    return IMPL.gw_alarm_delete(context, alarm_id)


def gw_alarm_get_all(context, limit, sort_keys, marker,
                     sort_dir, filters, tenant_safe=True):
    return IMPL.gw_alarm_get_all(context, tenant_safe)


def gw_alarm_get_all_by_group(context, group_id):
    return IMPL.gw_alarm_get_all_by_group(context, group_id)


def gw_group_create(context, values):
    return IMPL.gw_group_create(context, values)


def gw_group_delete(context, group_id):
    return IMPL.gw_group_delete(context, group_id)


def gw_group_get(context, group_id):
    return IMPL.gw_group_get(context, group_id)


def gw_group_get_all(context):
    return IMPL.gw_group_get_all(context)


def gw_group_update(context, group_id, values):
    return IMPL.gw_group_update(context, group_id, values)


def gw_member_get_all_by_group(context, group_id):
    return IMPL.gw_member_get_all_by_group(context, group_id)


def gw_member_delete_by_group_id(context, group_id):
    return IMPL.gw_member_delete_by_group_id(context, group_id)


def gw_member_delete_all(context, group_id):
    return IMPL.gw_member_delete_all(context, group_id)


def gw_member_create(context, values):
    return IMPL.gw_member_create(context, values)


def gw_member_delete(context, member_id):
    return IMPL.gw_member_delete(context, member_id)


def gw_member_get(context, member_id):
    return IMPL.gw_member_get(context, member_id)


def reset_stack_status(context, stack_id):
    return IMPL.reset_stack_status(context, stack_id)
