class AlarmsManager(object):
    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('POST', '/alarms',
                                              data=kwargs, headers=headers)
        return body

    def list(self):
        pass

    def get(self, alarm_id):
        resp, body = self.client.json_request('GET', '/alarms/%s' % alarm_id)
        return body

    def update(self, alarm_id, **kwargs):
        for k, v in kwargs.items():
            if not v:
                kwargs.pop(k)
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('PUT', '/alarms/%s' % alarm_id,
                                              data=kwargs, headers=headers)
        return body

    def delete(self, alarm_id):
        self.client.delete("/alarms/%s" % alarm_id)
