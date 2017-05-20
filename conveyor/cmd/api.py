#!/usr/bin/python
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Starter script for Cinder OS API."""

import eventlet

import os
import sys
import warnings

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.common import config  # noqa
from conveyor import i18n
from conveyor import rpc
from conveyor import service
from conveyor import utils
from conveyor import version

eventlet.monkey_patch()

warnings.simplefilter('once', DeprecationWarning)

possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, "conveyor", "__init__.py")):
    sys.path.insert(0, possible_topdir)

i18n.enable_lazy()

CONF = cfg.CONF


def main():
    logging.register_options(CONF)
    CONF(sys.argv[1:], project='conveyor',
         version=version.version_string())
    logging.setup(CONF, "conveyor")
    utils.monkey_patch()

    rpc.init(CONF)
    launcher = service.process_launcher()
    server = service.WSGIService('osapi_clone')
    launcher.launch_service(server, workers=server.workers)
    launcher.wait()
