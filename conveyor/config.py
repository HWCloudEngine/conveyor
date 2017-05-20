# Copyright 2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Wrapper for keystone.common.config that configures itself on import."""

from oslo_config import cfg
from oslo_db import options
from oslo_log import log

from conveyor import debugger
from conveyor import paths
from conveyor import rpc
import version

_DEFAULT_SQL_CONNECTION = 'sqlite:///' + \
                          paths.state_path_def('conveyor.sqlite')

CONF = cfg.CONF


def parse_args(argv, default_config_files=None):
    log.register_options(CONF)
    options.set_defaults(CONF, connection=_DEFAULT_SQL_CONNECTION,
                         sqlite_db='conveyor.sqlite')
    rpc.set_defaults(control_exchange='conveyor')
    debugger.register_cli_opts()
    CONF(argv[1:],
         project='conveyor',
         version=version.version_string(),
         default_config_files=default_config_files)
    rpc.init(CONF)
