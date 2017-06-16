# Copyright 2011 Justin Santa Barbara
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

"""The conveyor api."""
import ConfigParser
from webob import exc

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

from conveyor.api.wsgi import wsgi
from conveyor.db import api as db_api
from conveyor import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ConfigurationController(wsgi.Controller):
    """The Configuration API controller for the Conveyor API."""

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self.config_ctl = ConfigParser.ConfigParser()
        super(ConfigurationController, self).__init__()

    def show(self, req, id):
        """Return data about the given configure."""
        pass

    def delete(self, req, id):
        """Delete resource."""
        config_vaule = CONF.vgw_info
        config_value_str = '{' + config_vaule + '}'
        config_value_dict = eval(config_value_str)
        utils.remove_vgw_info(id, 'vgw_info', config_value_dict)
        LOG.debug('Config vgw info: %s', CONF.vgw_info)

    def index(self, req):
        """Returns a summary list of configure."""
        pass

    def detail(self, req):
        """Returns a detailed list of configure."""
        pass

    @wsgi.response(202)
    def create(self, req, body):
        """Creates a new configure."""
        if not self.is_valid_body(body, 'configurations'):
            LOG.debug("Configuration modify request body has not key:values")
            raise exc.HTTPUnprocessableEntity()

        config = body['configurations']

        # 1. add config vaule according key to system
        newConfig = None
        saveFileConfig = None
        filepath = config.get("config_file", CONF.config_path)
        config_body = config.get("config_info")

        # may be many conveyor-agents register wgv to conveyor
        # at the same time, so need lock vgw_info memory
        try:
            # 1.1 read config file info
            fh = None
            self.config_ctl.read(filepath)
            # 1.2 get all modify config value in request
            for configs in config_body:
                group = configs.pop('group', 'DEFAULT')
                for key, value in configs.items():
                    if 'DEFAULT' == group:
                        config_value = getattr(CONF, key, None)
                    else:
                        config_value = getattr(eval("CONF." + group),
                                               key, None)

                    if isinstance(config_value, dict) and (isinstance(value,
                                                                      dict)):
                        for k, v in value.items():
                            config_value[k] = v
                        newConfig = config_value

                        # change dict to string and remove '{}',
                        # eg:{'a':'aa','b':'bb'} to "'a':'aa','b':'bb'"
                        saveFileConfig = self._dict_to_string(newConfig)
                    elif isinstance(config_value, str) and (isinstance(value,
                                                                       dict)):
                            newConfig = self._regist_new_config(config_value,
                                                                value)
                            saveFileConfig = newConfig
                    elif isinstance(config_value, list) and (isinstance(value,
                                                                        list)):
                        for v in value:
                            config_value.append(v)
                        newConfig = config_value
                        saveFileConfig = self._list_to_string(newConfig)
                    else:
                        if isinstance(config_value, list):
                            config_value.append(value)
                            newConfig = config_value
                            saveFileConfig = self._list_to_string(newConfig)
                        elif (isinstance(config_value, dict)):
                            LOG.error("Add configure %(key)s : %(value)s,"
                                      "error: Type does not match,"
                                      "value is not dict,but config file"
                                      "the value of this key is dict",
                                      {'key': key, 'value': value})
                            continue
                        else:
                            newConfig = value
                            saveFileConfig = value

                    # 1.3 modify system config info
                    if 'DEFAULT' == group:
                        setattr(CONF, key, newConfig)
                    else:
                        setattr(eval("CONF." + group), key, newConfig)

                    # 2 add config value to config file
                    self.config_ctl.set(group, key, saveFileConfig)

            # write new info to config file
            fh = open(filepath, 'w')
            self.config_ctl.write(fh)

        except Exception as e:
                LOG.error("Add config info error: %s", e)
                if fh:
                    fh.close()
        finally:
            if fh:
                fh.close()

    def update(self, req, id, body):
        """Update a configure."""
        pass

    @utils.synchronized('conveyor-config', external=True)
    def _regist_new_config(self, config_vaule, add_value):

        # 1.transform config value to dict
        config_value_str = '{' + config_vaule + '}'

        try:
            config_value_dict = eval(config_value_str)
        except Exception as e:
            LOG.error("Update configuration error: %s", e)
            raise

        for k, v in add_value.items():
            config_az_value = config_value_dict.get(k, None)

            # if add key not exist, new one
            if not config_az_value:
                config_az_value = {}
            if isinstance(v, dict):
                for kk, vv in v.items():
                    config_az_value[kk] = vv
                    # add update time
                    utils.vgw_update_time[kk] = timeutils.utcnow()
                config_value_dict[k] = config_az_value
            else:
                config_value_dict[k] = v

        # transform config value to string
        config_value_str = str(config_value_dict)
        if (len(config_value_str) > 2):
            config_value_str = config_value_str[1:-1]
        else:
            config_value_str = ""

        LOG.debug('Add config info end, update time list: %s',
                  utils.vgw_update_time)

        return config_value_str

    def _dict_to_string(self, map):
        '''change dict to 'k:v,k:v' '''
        LOG.debug("Dict to string start, dict is: %s", map)
        map_str = ''
        i = 1
        for k, v in map.items():
            if i < len(map):
                map_str += k + ':' + v + ','
            else:
                map_str += k + ':' + v
            i += 1

        LOG.debug("Dict to string end, String is: %s", map_str)
        return map_str

    def _list_to_string(self, list_p):
        '''change dict to 'a,b,c' '''
        LOG.debug("List to string start, list is: %s", list)
        list_str = ''
        # remove duplicate value
        list_p = list(set(list_p))
        i = 1
        for l in list_p:
            if i < len(list_p):
                list_str += l + ','
            else:
                list_str += l
            i += 1

        LOG.debug("List to string end, string is: %s", list_str)
        return list_str

    @wsgi.response(202)
    @wsgi.action('register')
    def register(self, req, id, body):
        """register config."""

        if not self.is_valid_body(body, 'register'):
            msg = "Incorrect request body format."
            raise exc.HTTPBadRequest(explanation=msg)

        context = req.environ['conveyor.context']
        values = body['register']

        if not values:
            msg = 'No configurations found in body.'
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            for key, value in values.items():
                db_api.conveyor_config_create(context,
                                              {'config_key': key,
                                               'config_value': value})
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


def create_resource(ext_mgr):
    return wsgi.Resource(ConfigurationController(ext_mgr))
