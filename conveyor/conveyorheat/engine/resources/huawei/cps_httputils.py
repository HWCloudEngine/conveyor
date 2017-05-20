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

try:
    import ConfigParser
except ImportError:
    try:
        import configparser as ConfigParser
    except ImportError:
        pass

import json
import os
import requests
from threading import Lock
import traceback


from oslo_log import log as logging

from FSSecurity import crypt


LOG = logging.getLogger(__name__)

CPS_URL = 'cps_url'
CPS_USER_SECTION = 'system_account'
CPS_USER_KEY = 'cps_user'
CPS_PWD_KEY = 'cps_password'

CFG_FILE = '/etc/huawei/fusionsphere/heat.heat/cfg/heat.heat.cfg'
SYS_FILE = '/etc/huawei/fusionsphere/cfg/sys.ini'


class CPSHTTPException(Exception):
    """Base CPSHTTP exception.

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """
    s_message = 'An unknown exception occurred with http api'

    def __init__(self, message=None, *args, **kwargs):
        if not message:
            message = self.s_message
        try:
            message = message % kwargs
        except Exception:
            # at least get the core message out if something happened
            pass

        super(CPSHTTPException, self).__init__(message)


class CpsHTTPClient(object):
    CONFIG_DATA = None
    CONFIG_DATA_LOCK = Lock()

    @staticmethod
    def get_value_from_ini(file_path, option):
        with CpsHTTPClient.CONFIG_DATA_LOCK:
            if (CpsHTTPClient.CONFIG_DATA and
                    option in CpsHTTPClient.CONFIG_DATA):
                return CpsHTTPClient.CONFIG_DATA.get(option)

            if not file_path or not os.path.isfile(file_path):
                msg = "getValueFromINI:file is wrong.file is %s." % file_path
                raise CPSHTTPException(msg)

            privateCfgFile = file(file_path)
            configData = json.loads(privateCfgFile.read())
            CpsHTTPClient.CONFIG_DATA = configData

            return CpsHTTPClient.CONFIG_DATA.get(option)

    @staticmethod
    def get_cps_header():
        header = {}
        try:
            sysfile_conf = ConfigParser.RawConfigParser()
            sysfile_conf.read(SYS_FILE)
            user_name = sysfile_conf.get(CPS_USER_SECTION, CPS_USER_KEY)
            user_pwd = sysfile_conf.get(CPS_USER_SECTION, CPS_PWD_KEY)

            header['X-Auth-User'] = user_name
            header['X-Auth-Password'] = crypt.decrypt(user_pwd)
        except Exception as e:
            LOG.error("fail to get token: %s, error is %s." %
                      (traceback.format_exc(), e))
            header = {}

        return header

    @staticmethod
    def rest_cps_execute(opt, uri, body=None, time=None, verify=False):
        try:
            cps_uri = CpsHTTPClient.get_value_from_ini(CFG_FILE, CPS_URL)
            rest_ur = cps_uri + uri
            LOG.info("begin to rest_cps_execute, opt is %s, uri is %s,"
                     "time is %s, rest_ur is %s."
                     % (str(opt), str(uri), str(time), str(rest_ur)))

            response = requests.request(opt, rest_ur, verify=verify,
                                        headers=CpsHTTPClient.get_cps_header(),
                                        data=body, timeout=time)
            ret = (response.status_code, response.text)
        except Exception:
            LOG.error("connect http server fail,token second: %s" %
                      traceback.format_exc())
            return None

        LOG.info("end to rest_cps_execute,ret is %s." % str(ret))
        return ret
