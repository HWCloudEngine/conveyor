
class Alarm(object):
    def __init__(self, **kwargs):
        self.alarm_id = kwargs.get('')
        self.status = kwargs.get('')


class AlarmManager(object):
    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('POST', '/alarms',
                                              data=kwargs, headers=headers)
        return body

    def get(self, alarm_id):
        resp, body = self.client.json_request('GET', '/alarms/%s' % alarm_id)
        return Alarm(body)

    def update(self, alarm_id, **kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('PUT', '/alarms/%s' % alarm_id,
                                              data=kwargs, headers=headers)

    def delete(self, alarm_id):
        self.client.delete("/alarms/%s" % alarm_id)

    def suspend(self, alarm_id):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('PUT',
                                              '/alarms/%s/action' % alarm_id,
                                              data={'alarm_enabled': False},
                                              headers=headers)

    def resume(self, alarm_id):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('PUT',
                                              '/alarms/%s/action' % alarm_id,
                                              data={'alarm_enabled': True},
                                              headers=headers)
