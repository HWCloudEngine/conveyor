#!/usr/bin/env python
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

"""GroupWatch API Server.

An OpenStack ReST API to GroupWatch.
"""

import eventlet
eventlet.monkey_patch(os=False)

import sys

from oslo_config import cfg
import oslo_i18n as i18n
from oslo_log import log as logging
from oslo_reports import guru_meditation_report as gmr
from oslo_service import systemd
import six

from conveyor.conveyorheat.common import config
from conveyor.conveyorheat.common.i18n import _LI
from conveyor.conveyorheat.common import messaging
from conveyor.conveyorheat.common import profiler
from conveyor.conveyorheat.common import wsgi
from conveyor.conveyorheat import version

i18n.enable_lazy()

LOG = logging.getLogger('groupwatch.api')


def main():
    try:
        logging.register_options(cfg.CONF)
        cfg.CONF(project='heat', prog='groupwatch-api',
                 version=version.version_info.version_string())
        # change log format string for logging to the groupwatch file
        cfg.CONF.logging_context_format_string = \
            cfg.CONF.logging_context_format_string.replace('heat',
                                                           'groupwatch')
        cfg.CONF.logging_default_format_string = \
            cfg.CONF.logging_default_format_string.replace('heat',
                                                           'groupwatch')
        logging.setup(cfg.CONF, 'groupwatch')
        config.set_config_defaults()
        messaging.setup()

        app = config.load_paste_app()

        port = cfg.CONF.groupwatch_api.bind_port
        host = cfg.CONF.groupwatch_api.bind_host
        LOG.info(_LI('Starting GroupWatch REST API on %(host)s:%(port)s'),
                 {'host': host, 'port': port})
        profiler.setup('groupwatch-api', host)
        gmr.TextGuruMeditation.setup_autorun(version)
        server = wsgi.Server('groupwatch-api', cfg.CONF.groupwatch_api)
        server.start(app, default_port=port)
        systemd.notify_once()
        server.wait()
    except RuntimeError as e:
        msg = six.text_type(e)
        sys.exit("ERROR: %s" % msg)
