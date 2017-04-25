class SchedulerManager(object):
    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        headers = self.client.credentials_headers()
        if 'cover_flag' not in kwargs.keys():
            kwargs['cover_flag'] = True

        resp, body = self.client.json_request('POST', '/task',
                                              data=kwargs, headers=headers)
        return body

    def delete(self, task_id):
        self.client.delete("/task/%s" % task_id)
