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
