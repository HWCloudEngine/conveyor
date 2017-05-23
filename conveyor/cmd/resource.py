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

import eventlet
import os
import sys
import warnings

from oslo_config import cfg
from oslo_log import log as logging
from oslo_reports import guru_meditation_report as gmr

from conveyor import i18n
from conveyor import service
from conveyor import utils
from conveyor import version

# Need to register global_opts
from conveyor.common import config  # noqa
from conveyor.conveyorheat.common import config as heat_config
from conveyor.conveyorheat.common.i18n import _LC
from conveyor.conveyorheat.engine import template

if os.name == 'nt':
    # eventlet monkey patching the os module causes subprocess.Popen to fail
    # on Windows when using pipes due to missing non-blocking IO support.
    eventlet.monkey_patch(os=False)
else:
    eventlet.monkey_patch()

warnings.simplefilter('once', DeprecationWarning)


possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'conveyor', '__init__.py')):
    sys.path.insert(0, possible_topdir)

i18n.enable_lazy()


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
    init_heat()
    utils.monkey_patch()
    server = service.Service.create(binary='conveyor-resource')
    service.serve(server)
    service.wait()
