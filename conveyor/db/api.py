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

Functions in this module are imported into the conveyor.db namespace. Call these
functions from conveyor.db namespace, not the conveyor.db.api namespace.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.

"""

from oslo_config import cfg
from oslo_db import concurrency

from conveyor.i18n import _
from oslo_log import log as logging


db_opts = [
]

CONF = cfg.CONF
CONF.register_opts(db_opts)

_BACKEND_MAPPING = {'sqlalchemy': 'conveyor.db.sqlalchemy.api'}


IMPL = concurrency.TpoolDbapiWrapper(CONF, backend_mapping=_BACKEND_MAPPING)

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

def plan_get_all(context):
    """get all plans."""
    return IMPL.plan_get_all(context)



