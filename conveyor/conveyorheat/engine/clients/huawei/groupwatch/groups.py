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


class GroupsManager(object):
    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('POST', '/groups',
                                              data=kwargs, headers=headers)
        return body

    def delete(self, group_id):
        self.client.delete("/groups/%s" % group_id)

    def update(self, group_id, **kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('PUT', '/groups/%s' % group_id,
                                              data=kwargs, headers=headers)
        return body

    def get(self, group_id):
        resp, body = self.client.json_request('GET', '/groups/%s' % group_id)
        return body

    def list(self):
        pass
