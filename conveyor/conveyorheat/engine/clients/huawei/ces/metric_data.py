

class MetricDataManager(object):
    def __init__(self, client):
        self.client = client

    def create(self, kwargs):
        headers = self.client.credentials_headers()
        resp, body = self.client.json_request('POST', '/metric-data',
                                              data=kwargs, headers=headers)
        return body

    def get(self, **kwargs):
        def format_params(**kwargs):
            params = []
            for k, v in kwargs.items():
                params.append('%s=%s' % (k, v))
            return '&'.join(params)

        dimensions = kwargs.pop('dimensions', None)
        if dimensions:
            kwargs.update({
                'dim.0': '%s,%s' % (
                    dimensions[0].get('name'),
                    dimensions[0].get('value'))
            })

        query = format_params(**kwargs)
        resp, body = self.client.json_request('GET', '/metric-data?%s' % query)
        return body.get('datapoints')
