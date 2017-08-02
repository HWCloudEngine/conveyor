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

import os

from eventlet.green import socket
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


def get_hostid():
    """Get host id from uuid file."""

    hostid = ""
    file_path = "/etc/uuid"
    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r') as fp:
                hostid = fp.readline()
        except Exception:
            LOG.warning("read uuid file fail, try hosts file")
            hostid = socket.gethostname()
    else:
        LOG.warning("uuid file not exist, use hosts file")
        hostid = socket.gethostname()
    return hostid
