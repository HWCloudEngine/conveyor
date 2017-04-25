# Copyright 2011 Nebula, Inc.
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

from oslo_log import log as logging

from conveyor.conveyorheat.common.huawei.identity import HuaweiAuth
from conveyor.conveyorheat.common.huawei.trusts import HuaweiTrustManager

from keystoneclient.auth.identity import v3 as v3_auth
from keystoneclient import exceptions
from keystoneclient.v3 import client

LOG = logging.getLogger(__name__)


class Client(client.Client):
    """Huawei Extended Client for the OpenStack Identity API v3.

    Extened client for OpenStack Identity API v3
    """

    def __init__(self, **kwargs):
        """Initialize a new client for the Keystone v3 API."""
        super(Client, self).__init__(**kwargs)

        # override TrustManager
        # list and show trust may be wrong.
        self.trusts = HuaweiTrustManager(self)

    def get_raw_token_from_identity_service(self, auth_url, user_id=None,
                                            username=None,
                                            user_domain_id=None,
                                            user_domain_name=None,
                                            password=None,
                                            domain_id=None, domain_name=None,
                                            project_id=None, project_name=None,
                                            project_domain_id=None,
                                            project_domain_name=None,
                                            token=None,
                                            trust_id=None,
                                            **kwargs):
        """Authenticate against the v3 Identity API.

        If password and token methods are both provided then both methods will
        be used in the request.

        :returns: access.AccessInfo if authentication was successful.
        :raises: AuthorizationFailure if unable to authenticate or validate
                 the existing authorization token
        :raises: Unauthorized if authentication fails due to invalid token

        """
        try:
            if auth_url is None:
                raise ValueError("Cannot authenticate without an auth_url")

            auth_methods = []

            if token:
                auth_methods.append(v3_auth.TokenMethod(token=token))

            if password:
                m = v3_auth.PasswordMethod(user_id=user_id,
                                           username=username,
                                           user_domain_id=user_domain_id,
                                           user_domain_name=user_domain_name,
                                           password=password)
                auth_methods.append(m)

            if not auth_methods:
                msg = 'A user and password or token is required.'
                raise exceptions.AuthorizationFailure(msg)

            plugin = HuaweiAuth(auth_url, auth_methods,
                                trust_id=trust_id,
                                domain_id=domain_id,
                                domain_name=domain_name,
                                project_id=project_id,
                                project_name=project_name,
                                project_domain_id=project_domain_id,
                                project_domain_name=project_domain_name)

            return plugin.get_auth_ref(self.session)
        except (exceptions.AuthorizationFailure, exceptions.Unauthorized):
            LOG.debug('Authorization failed.')
            raise
        except exceptions.EndpointNotFound:
            msg = 'There was no suitable authentication url for this request'
            raise exceptions.AuthorizationFailure(msg)
        except Exception as e:
            raise exceptions.AuthorizationFailure('Authorization failed: '
                                                  '%s' % e)
