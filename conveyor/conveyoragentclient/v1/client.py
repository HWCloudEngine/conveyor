# Copyright (c) 2013 OpenStack Foundation
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

from oslo_config import cfg

from conveyor.conveyoragentclient import client
from conveyor.conveyoragentclient.v1 import birdiegatewayservice

client_opts = [
    cfg.StrOpt('gateway_protocol',
               default='http',
               help='conveyor gateway service api protocol(http or https) '),
    cfg.IntOpt('conveyoragent_timeout',
               default=300,
               help='conveyor gateway service api time out '),
    cfg.IntOpt('conveyoragent_retries',
               default=10,
               help='conveyor gateway service api time out '),
    ]
CONF = cfg.CONF
CONF.register_opts(client_opts)


def get_birdiegateway_client(host, port, version='v1'):

    client = Client(host=host, port=port,
                    birdie_gateway_version=version)

    return client


class Client(object):
    """
    Top-level object to access the OpenStack Volume API.

    Create an instance with your creds::

        >>> client = Client(USERNAME, PASSWORD, PROJECT_ID, AUTH_URL)

    Then call methods on its managers::

        >>> client.volumes.list()
        ...

    """

    def __init__(self, username=None, api_key=None, project_id=None,
                 host='0.0.0.0', port='9998', birdie_gateway_version="v1",
                 auth_url='', insecure=False, timeout=None, tenant_id=None,
                 proxy_tenant_id=None, proxy_token=None, region_name=None,
                 extensions=None, service_name=None, retries=None,
                 http_log_debug=False, cacert=None, auth_system=None,
                 auth_plugin=None, session=None, **kwargs):
        # FIXME(comstud): Rename the api_key argument above when we
        # know it's not being used as keyword argument
        password = api_key
        proto = CONF.gateway_protocol
        if not proto.endswith("://"):
            proto += "://"

        self.url = proto + host + ":" + port + "/" + birdie_gateway_version

        if not timeout:
            timeout = CONF.conveyoragent_timeout
        if not retries:
            retries = CONF.conveyoragent_retries

        self.client = client._construct_http_client(
            username=username,
            password=password,
            project_id=project_id,
            auth_url=auth_url,
            insecure=insecure,
            timeout=timeout,
            tenant_id=tenant_id,
            proxy_tenant_id=tenant_id,
            proxy_token=proxy_token,
            region_name=region_name,
            service_name=service_name,
            retries=retries,
            http_log_debug=http_log_debug,
            cacert=cacert,
            auth_system=auth_system,
            auth_plugin=auth_plugin,
            session=session,
            **kwargs)

        # extensions
        self.vservices = birdiegatewayservice.VServiceManager(self.client,
                                                              self.url)

    def authenticate(self):
        """
        Authenticate against the server.

        Normally this is called automatically when you first access the API,
        but you can call this method to force authentication right now.

        Returns on success; raises :exc:`exceptions.Unauthorized` if the
        credentials are wrong.
        """
        pass
