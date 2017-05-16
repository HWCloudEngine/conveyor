#!/usr/bin/python
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

"""Starter script for Cinder Volume."""

import os

import eventlet

if os.name == 'nt':
    # eventlet monkey patching the os module causes subprocess.Popen to fail
    # on Windows when using pipes due to missing non-blocking IO support.
    eventlet.monkey_patch(os=False)
else:
    eventlet.monkey_patch()

import sys
import warnings

warnings.simplefilter('once', DeprecationWarning)

from oslo_config import cfg

# If ../cinder/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'cinder', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from conveyor import i18n
i18n.enable_lazy()

# Need to register global_opts
from conveyor.common import config  # noqa
from oslo_log import log as logging
from conveyor import service
from conveyor import utils
from conveyor import version
from conveyor.conveyorheat.engine import template
from conveyor.conveyorheat.common.i18n import _LC
from oslo_reports import guru_meditation_report as gmr
from conveyor.conveyorheat.common import config as heat_config


host_opt = cfg.StrOpt('host',
                      help='Backend override of host value.')
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def init_heat():
    heat_config.startup_sanity_check()

    mgr = None
    try:
        mgr = template._get_template_extension_manager()
    except template.TemplatePluginNotRegistered as ex:
        LOG.critical(_LC("%s"), ex)
    if not mgr or not mgr.names():
        sys.exit("ERROR: No template format plugins registered")
    gmr.TextGuruMeditation.setup_autorun(version)


def main():
    logging.register_options(CONF)
    CONF(sys.argv[1:], project='conveyor',
         version=version.version_string())
    logging.setup(CONF, "conveyor")
    utils.monkey_patch()
    init_heat()
    launcher = service.get_launcher()
    server = service.Service.create(binary='conveyor-clone')
    launcher.launch_service(server)
    launcher.wait()
