#!/usr/bin/env python
# Copyright 2012 OpenStack Foundation
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

"""Utilities and helper functions."""

from oslo_config import cfg
from oslo_serialization import jsonutils

from conveyor import exception
from conveyor.i18n import _

CONF = cfg.CONF


class LazyPluggable(object):
    """A pluggable backend loaded lazily based on some value."""

    def __init__(self, pivot, config_group=None, **backends):
        self.__backends = backends
        self.__pivot = pivot
        self.__backend = None
        self.__config_group = config_group

    def __get_backend(self):
        if not self.__backend:
            if self.__config_group is None:
                backend_name = CONF[self.__pivot]
            else:
                backend_name = CONF[self.__config_group][self.__pivot]
            if backend_name not in self.__backends:
                msg = _('Invalid backend: %s') % backend_name
                raise exception.V2vException(msg)

            backend = self.__backends[backend_name]
            if isinstance(backend, tuple):
                name = backend[0]
                fromlist = backend[1]
            else:
                name = backend
                fromlist = backend

            self.__backend = __import__(name, None, None, fromlist)
        return self.__backend

    def __getattr__(self, key):
        backend = self.__get_backend()
        return getattr(backend, key)


class SmarterEncoder(jsonutils.json.JSONEncoder):
    """Help for JSON encoding dict-like objects."""
    def default(self, obj):
        if not isinstance(obj, dict) and hasattr(obj, 'iteritems'):
            return dict(obj.iteritems())
        return super(SmarterEncoder, self).default(obj)


def utf8(value):
    """Try to turn a string into utf-8 if possible.

    Code is directly from the utf8 function in
    http://github.com/facebook/tornado/blob/master/tornado/escape.py

    """
    if isinstance(value, unicode):
        return value.encode('utf-8')
    assert isinstance(value, str)
    return value


def get_value_from_dict(d, keys):
    """return value from d in keys. """
    if not d:
        return None
    for k in keys:
        if k in d:
            return d[k]
        for v in d.values():
            if type(v) == dict:
                r = get_value_from_dict(v, keys)
                if r:
                    return r
    return None


IMPL = LazyPluggable('backend',
                     sqlalchemy='conveyor.db.sqlalchemy.api')


def purge_deleted(age, granularity='days'):
    IMPL.purge_deleted(age, granularity)


def encrypt_parameters_and_properties(ctxt, encryption_key):
    IMPL.db_encrypt_parameters_and_properties(ctxt, encryption_key)


def decrypt_parameters_and_properties(ctxt, encryption_key):
    IMPL.db_decrypt_parameters_and_properties(ctxt, encryption_key)
