# Copyright (c) 2011 OpenStack Foundation
# Copyright 2010 Jacob Kaplan-Moss
# Copyright 2011 Piston Cloud Computing, Inc.
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
from keystoneclient import access
from conveyor import exception
from oslo.config import cfg
import requests

from conveyor.common import log as logging

try:
    import json
except ImportError:
    import simplejson as json

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

CONF.import_opt('auth_protocol', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_host', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_port', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_version', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')
CONF.import_opt('auth_admin_prefix', 'keystoneclient.middleware.auth_token',
                group='keystone_authtoken')


ENDPOINT_TYPE_TO_INTERFACE = {
    'publicURL': 'publicurl',
    'internalURL': 'internal',
    'adminURL': 'internalurl',
}

class Client(object):
    
    def __init__(self, auth_url=None, user=None, password=None,
                 projectid=None, tenant_id=None, region_name=None,
                 endpoint_type='publicURL', service_type=None,
                 auth_token=None, timeout=None):

        auth_url = "%s://%s:%s/%s/%s" % (
                        CONF.keystone_authtoken.auth_protocol,
                        CONF.keystone_authtoken.auth_host,
                        CONF.keystone_authtoken.auth_port,
                        CONF.keystone_authtoken.auth_admin_prefix,
                        CONF.keystone_authtoken.auth_version)
     
        self.auth_url = auth_url
        self.user = user
        self.password = password
        self.projectid = projectid
        self.tenant_id = tenant_id
        self.region_name = region_name
        self.endpoint_type = endpoint_type
        self.service_type = service_type
        self.timeout = timeout
        self.auth_token = None
    
    def get_service_endpoint(self, context, service_type,
                             endpoint_type='publicURL', region_name=None):
        
        if not service_type:
            self.service_type = service_type
            
        self.endpoint_type = endpoint_type    

        #set token
        self.auth_token = context.auth_token  

        #2.get service id by service name
        service = self._get_service_id(service_type)
        #3. get service endpoint
        url = self._get_service_endpoint(service, endpoint_type)
        
        url = self._replace_tenant_id(context, url)    

        return url   
    
    def _get_service_id(self, service_type):
        
        headers = {'X-Auth-Token': self.auth_token}
        service_url = self.auth_url + '/OS-KSADM/services'
        resp, body = self.request(service_url, 'GET', headers=headers)
        services = body.get('OS-KSADM:services')
        LOG.debug("Query service list: %s", services)
        
        for service in services:
            if service_type == service.get('type'):
                return service.get('id')
        
        return None
            
    
    def _get_service_endpoint(self, service, endpoint_type, region_name=None):
        headers = {'X-Auth-Token': self.auth_token}
        url = self.auth_url + '/endpoints'
        resp, body = self.request(url, 'GET', headers=headers)
        
        endpoints = body.get('endpoints')
        
        endpointType = ENDPOINT_TYPE_TO_INTERFACE.get(endpoint_type)
        region_name = region_name or CONF.os_region_name
        
        if not endpointType:
            LOG.error("Input endpoint type error: %s, only valid(publicURL/internalURL/adminURL)", endpoint_type)
            return None
        endpoint_url = None
        for endpoint in endpoints:
            if service == endpoint.get('service_id') and \
            region_name == endpoint.get('region'):
                endpoint_url = endpoint.get(endpointType)
                break
            
        return endpoint_url
    
    def _replace_tenant_id(self, context, endpoint):
        '''URL maybe is: https://ip:port/v1/$(tenant_id)s, here
        replace $(tenant_id)s as tenant id value'''
      
        ls = endpoint.split('$(tenant_id)s')
        url = ls[0]
        if len(ls) < 2:
            return url
        else:
            ls.pop(0)
            for l in ls:
                url += context.project_id + l
            return url.lstrip()


                
    
    def request(self, url, method, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        kwargs['headers']['User-Agent'] = 'python-keystoneclient'
        kwargs['headers']['Accept'] = 'application/json'

        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['data'] = json.dumps(kwargs['body'])
            del kwargs['body']

        if self.timeout:
            kwargs.setdefault('timeout', self.timeout)
        resp = requests.request(
            method,
            url,
            verify=False,
            **kwargs)

        if resp.text:
            try:
                body = json.loads(resp.text)
            except ValueError:
                pass
                body = None
        else:
            body = None

        if resp.status_code >= 400:
            raise exception.ConvertedException(code=resp.status_code,explanation=resp.text)

        return resp, body