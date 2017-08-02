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

from oslo_log import log as logging

from keystoneclient.auth.identity.v3 import Auth

LOG = logging.getLogger(__name__)


class HuaweiAuth(Auth):
    @property
    def token_url(self):
        """The full URL where we will send authentication data."""
        if self.is_trust_token_request():
            return '%s/auth/tokens-trust-ext' % self.auth_url.rstrip('/')
        else:
            return super(HuaweiAuth, self).token_url

    def is_trust_token_request(self):
        if (self.domain_id or self.domain_name or
                self.project_id or self.project_name):
            return False
        elif self.trust_id:
            return True

        return False
