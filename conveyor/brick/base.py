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
"""
Helper code for the iSCSI volume driver.

"""

import six
from conveyor import utils
from conveyor.common import log as logging


LOG = logging.getLogger(__name__)


    
class MigrationCmd(object):
    
    def __init__(self, execute=utils.execute): 
        self._execute = execute
    
    def check_ip_connect(self, ip):
        try:
            (out, err) = self._execute('ping', '-c', '4', ip, run_as_root=True)
        except Exception as e:
            LOG.error("Ping Ip %(ip)s failed: %(error)s",
                      {'ip': ip, 'error': e})
            
            return False
        return True
  
    
