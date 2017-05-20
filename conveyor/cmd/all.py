#!/usr/bin/env python
# Copyright 2011 OpenStack, LLC
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

"""Starter script for All v2vgateway services.

This script attempts to start all the cinder services in one process.  Each
service is started in its own greenthread.  Please note that exceptions and
sys.exit() on the starting of a service are logged and the script will
continue attempting to launch the rest of the services.

"""

import sys
import warnings

from oslo_config import cfg
from oslo_log import log as logging

from conveyor.i18n import _LE

from conveyor import config
from conveyor import service


from conveyor import i18n

warnings.simplefilter('once', DeprecationWarning)

i18n.enable_lazy()

CONF = cfg.CONF


def main():
    config.parse_args(sys.argv)
    logging.setup(CONF, "conveyor")
    LOG = logging.getLogger('v2v_all')

    launcher = service.process_launcher()
    # conveyor-api
    try:
        server = service.WSGIService('osapi_v2v')
        launcher.launch_service(server, workers=server.workers or 1)
    except (Exception, SystemExit):
        LOG.exception(_LE('Failed to load conveyor-api'))

    for binary in ['conveyor-clone']:
        try:
            launcher.launch_service(service.Service.create(binary=binary))
        except (Exception, SystemExit):
            LOG.exception(_LE('Failed to load %s'), binary)
    launcher.wait()
