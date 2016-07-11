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
import webob
from webob import exc

from oslo.config import cfg

from conveyor.common import log as logging
from conveyor.api.wsgi import wsgi

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
        pass

    def index(self, req):
        """Returns a summary list of configure."""
        pass

    def detail(self, req):
        """Returns a detailed list of configure."""
        pass

    @wsgi.response(202)
    def create(self, req, body):
        """Creates a new configure."""
        if  not self.is_valid_body(body, 'configurations'):
            LOG.debug("Configuration modify request body has not key:configurations")
            raise exc.HTTPUnprocessableEntity()
        
        config = body['configurations']
        
        # 1. add config vaule according key to system
        newConfig = None
        saveFileConfig = None
        filepath = config.get("config_file", CONF.config_path)
        config_body = config.get("config_info")
        try:
            # 1.1 read config file info
            self.config_ctl.read(filepath)
            #1.2 get all modify config value in request
            for configs in config_body:
                group = configs.pop('group') or 'DEFAULT'
                for key, value in configs.items():
                    config_value = getattr(CONF, key, None)
                    if not config_value:
                        LOG.error("Add configure %s is not support", key)
                        continue
                    
                    if config_value and (isinstance(value, dict)):
                        for k, v in value.items():
                            config_value[k] =  v
                        newConfig = config_value
                        
                        # change dict to string and remove '{}',
                        #eg:{'a':'aa','b':'bb'} to "'a':'aa','b':'bb'"
                        saveFileConfig = self._dict_to_string(newConfig)
                    elif config_value and (isinstance(value, list)):
                        for v in value:
                            config_value.append(v)
                        newConfig = config_value
                        saveFileConfig = self._list_to_string(newConfig)
                    else:
                        newConfig = value
                        saveFileConfig = value
                    
                    #1.3 modify system config info
                    setattr(CONF, key, newConfig)
                       
                    #2 add config value to config file
                    self.config_ctl.set(group, key, saveFileConfig)
            
            # write new info to config file
            fh = open(filepath ,'w')
            self.config_ctl.write(fh)
            
        except Exception as e:
                LOG.error("Add config info error: %s", e)
                fh.close()
        finally:
            if fh:
                fh.close()

    def update(self, req, id, body):
        """Update a configure."""
        pass
    
    def _dict_to_string(self, map):
        '''change dict to 'k:v,k:v' '''
        LOG.debug("Dict to string start, dict is: %s", map)
        map_str = ''
        i = 1
        for k, v in map.items():
            if i < len(map):
                map_str += k +':' + v + ','
            else:
                map_str += k +':' + v
            i += 1
        
        LOG.debug("Dict to string end, String is: %s", map_str)
        return map_str
    
    def _list_to_string(self, list):
        '''change dict to 'a,b,c' '''
        LOG.debug("List to string start, list is: %s", list)
        list_str = ''
        
        i = 1
        for l in list:
            if i < len(list):
                list_str += l + ','
            else:
                list_str += l
            i += 1
        
        LOG.debug("List to string end, string is: %s", list_str)
        return list_str
            


def create_resource(ext_mgr):
    return wsgi.Resource(ConfigurationController(ext_mgr))
