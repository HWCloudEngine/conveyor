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
"""
OpenStack Client interface. Handles the REST calls and responses.
"""

from __future__ import print_function

import logging

import requests

from conveyor.conveyoragentclient.common import exceptions
from conveyor.common import strutils
from conveyor.common import importutils as utils


try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

try:
    from eventlet import sleep
except ImportError:
    from time import sleep

try:
    import json
except ImportError:
    import simplejson as json

# Python 2.5 compat fix
if not hasattr(urlparse, 'parse_qsl'):
    import cgi
    urlparse.parse_qsl = cgi.parse_qsl

_VALID_VERSIONS = ['v1']


class HTTPClient(object):

    USER_AGENT = 'python-birdiegatewayclient'

    def __init__(self, user, password, projectid, auth_url=None,
                 insecure=False, timeout=None, tenant_id=None,
                 proxy_tenant_id=None, proxy_token=None, region_name=None,
                 service_name=None, retries=None,
                 http_log_debug=False, cacert=None,
                 auth_system=None, auth_plugin=None):
        self.user = user
        self.password = password
        self.projectid = projectid
        self.tenant_id = tenant_id

        self.auth_url = None
        self.version = 'v1'
        self.region_name = region_name
        self.service_name = service_name
        self.retries = int(retries or 0)
        self.http_log_debug = http_log_debug

        self.management_url = None
        self.auth_token = None
        self.proxy_token = proxy_token
        self.proxy_tenant_id = proxy_tenant_id
        self.timeout = timeout

        if insecure:
            self.verify_cert = False
        else:
            if cacert:
                self.verify_cert = cacert
            else:
                self.verify_cert = True

        self.auth_system = auth_system
        self.auth_plugin = auth_plugin

        self._logger = logging.getLogger(__name__)

    def http_log_req(self, args, kwargs):
        if not self.http_log_debug:
            return

        string_parts = ['curl -i']
        for element in args:
            if element in ('GET', 'POST', 'DELETE', 'PUT'):
                string_parts.append(' -X %s' % element)
            else:
                string_parts.append(' %s' % element)

        for element in kwargs['headers']:
            header = ' -H "%s: %s"' % (element, kwargs['headers'][element])
            string_parts.append(header)

        if 'data' in kwargs:
            if "password" in kwargs['data']:
                data = strutils.mask_password(kwargs['data'])
            else:
                data = kwargs['data']
            string_parts.append(" -d '%s'" % (data))
        self._logger.debug("\nREQ: %s\n" % "".join(string_parts))

    def http_log_resp(self, resp):
        if not self.http_log_debug:
            return
        self._logger.debug(
            "RESP: [%s] %s\nRESP BODY: %s\n",
            resp.status_code,
            resp.headers,
            resp.text)

    def request(self, url, method, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        kwargs['headers']['User-Agent'] = self.USER_AGENT
        kwargs['headers']['Accept'] = 'application/json'
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['data'] = json.dumps(kwargs['body'])
            del kwargs['body']

        if self.timeout:
            kwargs.setdefault('timeout', self.timeout)
        self.http_log_req((url, method,), kwargs)
        resp = requests.request(
            method,
            url,
            verify=self.verify_cert,
            **kwargs)
        self.http_log_resp(resp)

        if resp.text:
            try:
                body = json.loads(resp.text)
            except ValueError:
                pass
                body = None
        else:
            body = None

        if resp.status_code >= 400:
            raise exceptions.from_response(resp, body)

        return resp, body

    def _cs_request(self, url, method, **kwargs):
        auth_attempts = 0
        attempts = 0
        backoff = 1
        while True:
            attempts += 1
            #if not self.management_url or not self.auth_token:
            #   self.authenticate()
            #kwargs.setdefault('headers', {})['X-Auth-Token'] = self.auth_token
            #if self.projectid:
                #kwargs['headers']['X-Auth-Project-Id'] = self.projectid
            try:
                if self.management_url:
                    url = self.management_url + url
                resp, body = self.request(url, method,
                                          **kwargs)
                return resp, body
            except exceptions.BadRequest as e:
                if attempts > self.retries:
                    raise
            except exceptions.Unauthorized:
                if auth_attempts > 0:
                    raise
                self._logger.debug("Unauthorized, reauthenticating.")
                self.management_url = self.auth_token = None
                # First reauth. Discount this attempt.
                attempts -= 1
                auth_attempts += 1
                continue
            except exceptions.ClientException as e:
                if attempts > self.retries:
                    raise
                if 500 <= e.code <= 599:
                    pass
                else:
                    raise
            except requests.exceptions.ConnectionError as e:
                self._logger.debug("Connection error: %s" % e)
                if attempts > self.retries:
                    msg = 'Unable to establish connection: %s' % e
                    raise exceptions.ConnectionError(msg)
            self._logger.debug(
                "Failed attempt(%s of %s), retrying in %s seconds" %
                (attempts, self.retries, backoff))
            sleep(backoff)
            backoff *= 2

    def get(self, url, **kwargs):
        return self._cs_request(url, 'GET', **kwargs)

    def post(self, url, **kwargs):
        return self._cs_request(url, 'POST', **kwargs)

    def put(self, url, **kwargs):
        return self._cs_request(url, 'PUT', **kwargs)

    def delete(self, url, **kwargs):
        return self._cs_request(url, 'DELETE', **kwargs)



def _construct_http_client(username=None, password=None, project_id=None,
                           auth_url=None, insecure=False, timeout=None,
                           proxy_tenant_id=None, proxy_token=None,
                           region_name=None, 
                           service_name=None, 
                           retries=None,
                           http_log_debug=False,
                           auth_system=None, auth_plugin=None,
                           cacert=None, tenant_id=None,
                           session=None,
                           auth=None,
                           **kwargs):

        # FIXME(jamielennox): username and password are now optional. Need
        # to test that they were provided in this mode.
    return HTTPClient(username,
                      password,
                    projectid=project_id,
                    auth_url=auth_url,
                    insecure=insecure,
                    timeout=timeout,
                    tenant_id=tenant_id,
                    proxy_token=proxy_token,
                    proxy_tenant_id=proxy_tenant_id,
                    region_name=region_name,
                    service_name=service_name,
                    retries=retries,
                    http_log_debug=http_log_debug,
                    cacert=cacert,
                    auth_system=auth_system,
                    auth_plugin=auth_plugin,
                    )


def get_client_class(version):
    version_map = {
        'v1': 'conveyor.conveyoragentclient.v1.client.Client',
    }
    try:
        client_path = version_map[str(version)]
    except (KeyError, ValueError):
        msg = "Invalid client version '%s'. must be one of: %s" % (
            (version, ', '.join(version_map)))
        raise exceptions.UnsupportedVersion(msg)

    return utils.import_class(client_path)


def Client(version='v1', *args, **kwargs):
    client_class = get_client_class(version)
    return client_class(*args, **kwargs)
