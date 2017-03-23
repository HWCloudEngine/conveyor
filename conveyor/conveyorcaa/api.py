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

"""
Main abstraction layer for cloud adapter operations used by conveyor.
"""

import inspect

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service.loopingcall import RetryDecorator

from conveyor import exception

from conveyorcaaclient.client import Client
import conveyorcaaclient.exc

LOG = logging.getLogger(__name__)

conveyorcaa_opts = [
    cfg.StrOpt('conveyor_caa_ip',
               default='127.0.0.1',
               help='conveyorcaa service ip'),
    cfg.IntOpt('conveyor_caa_port',
               default=9997,
               help='conveyorcaa service port'),
    cfg.IntOpt('max_retry_count',
               default=5,
               help='conveyorcaa service port'),
    cfg.IntOpt('inc_sleep_time',
               default=2,
               help='conveyorcaa service port'),
    cfg.IntOpt('max_sleep_time',
               default=30,
               help='conveyorcaa service port')
]


CONF = cfg.CONF
CONF.register_opts(conveyorcaa_opts, group='conveyor_caa')


class ConveyorcaaClientWrapper(object):
    """conveyorcaa client wrapper class that implements retries."""

    def __init__(self):
        management_ip = CONF.conveyor_caa.conveyor_caa_ip
        port = CONF.conveyor_caa.conveyor_caa_port
        self.client = Client(management_ip, port)

    def call(self, method, *args, **kwargs):
        """Call a conveyorcaa client method.  If we get a connection error,
        retry the request.

        """
        @RetryDecorator(max_retry_count=CONF.conveyor_caa.max_retry_count,
                        inc_sleep_time=CONF.conveyor_caa.inc_sleep_time,
                        max_sleep_time=CONF.conveyor_caa.max_sleep_time,
                        exceptions=(
                                conveyorcaaclient.exc.ServiceUnavailable,
                                conveyorcaaclient.exc.CommunicationError,
                                exception.RetryException))
        def _call():
            result = getattr(self.client, method)(*args, **kwargs)
            if inspect.isgenerator(result):
                # Convert generator results to a list, so that we can
                # catch any potential exceptions now and retry the call.
                return list(result)
            return result

        return _call()
