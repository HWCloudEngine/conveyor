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
