# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
from oslo.config import cfg

from heatclient import client as heat_client

from conveyor import exception
from conveyor.common import log as logging

LOG = logging.getLogger(__name__)

heat_opts = [
    cfg.StrOpt('heat_url',
               default='https://127.0.0.1:8700/v1',
               help='Default heat URL',
               deprecated_group='DEFAULT',
               deprecated_name='heat_url')
    ]

CONF = cfg.CONF

CONF.register_opts(heat_opts, 'heat')
# Mapping of V2 Catalog Endpoint_type to V3 Catalog Interfaces
ENDPOINT_TYPE_TO_INTERFACE = {
    'publicURL': 'public',
    'internalURL': 'internal',
    'adminURL': 'admin',
}

def format_parameters(params):
    parameters = {}
    for count, p in enumerate(params, 1):
        parameters['Parameters.member.%d.ParameterKey' % count] = p
        parameters['Parameters.member.%d.ParameterValue' % count] = params[p]
    return parameters

def get_service_from_catalog(catalog, service_type):
    if catalog:
        for service in catalog:
            if 'type' not in service:
                continue
            if service['type'] == service_type:
                return service
    return None

def get_version_from_service(service):
    if service and service.get('endpoints'):
        endpoint = service['endpoints'][0]
        if 'interface' in endpoint:
            return 3
        else:
            return 2.0
    return 2.0


def _get_endpoint_region(endpoint):
    """Common function for getting the region from endpoint.

    In Keystone V3, region has been deprecated in favor of
    region_id.

    This method provides a way to get region that works for
    both Keystone V2 and V3.
    """
    return endpoint.get('region_id') or endpoint.get('region')

def get_url_for_service(service, endpoint_type, region=None):
    if 'type' not in service:
        return None

    identity_version = get_version_from_service(service)
    service_endpoints = service.get('endpoints', [])
    if region:
        available_endpoints = [endpoint for endpoint in service_endpoints
                               if region == _get_endpoint_region(endpoint)]
    else:
        available_endpoints = service_endpoints
    """if we are dealing with the identity service and there is no endpoint
    in the current region, it is okay to use the first endpoint for any
    identity service endpoints and we can assume that it is global
    """
    if service['type'] == 'identity' and not available_endpoints:
        available_endpoints = [endpoint for endpoint in service_endpoints]

    for endpoint in available_endpoints:
        try:
            if identity_version < 3:
                return endpoint.get(endpoint_type)
            else:
                interface = \
                    ENDPOINT_TYPE_TO_INTERFACE.get(endpoint_type, '')
                if endpoint.get('interface') == interface:
                    return endpoint.get('url')
        except (IndexError, KeyError):
            """it could be that the current endpoint just doesn't match the
            type, continue trying the next one
            """
            pass
    return None

def url_for(context, service_type, endpoint_type=None, region=None):
    endpoint_type = endpoint_type or getattr(CONF,
                                             'OPENSTACK_ENDPOINT_TYPE',
                                             'publicURL')
    fallback_endpoint_type = getattr(CONF, 'SECONDARY_ENDPOINT_TYPE', None)
    region = getattr(CONF, 'os_region_name', None)

    catalog = context.service_catalog
    service = get_service_from_catalog(catalog, service_type)
    if service:
        url = get_url_for_service(service,
                                  endpoint_type,
                                  region=region)
        if not url and fallback_endpoint_type:
            url = get_url_for_service(service,
                                      fallback_endpoint_type,
                                      region=region)
        if url:
            return url
    raise exception.ServiceCatalogException(service_type)

def heatclient(context, password=None):
    api_version = "1"
    insecure = getattr(CONF, 'OPENSTACK_SSL_NO_VERIFY', True)
    cacert = getattr(CONF, 'OPENSTACK_SSL_CACERT', None)
    try:
        endpoint = url_for(context, 'orchestration')
    except Exception as e:
        LOG.error("HeatClient get URL from context.service_catalog error: %s" % e)
        endpoint = CONF.heat.heat_url + '/' + context.project_id
    kwargs = {
        'token': context.auth_token,
        'insecure': insecure,
        'ca_file': cacert,
        'username': context.user_id,
        'password': password
        # 'timeout': args.timeout,
        # 'ca_file': args.ca_file,
        # 'cert_file': args.cert_file,
        # 'key_file': args.key_file,
    }
    client = heat_client.Client(api_version, endpoint, **kwargs)
    client.format_parameters = format_parameters
    return client



class API(object):
    
    def get_stack(self, context, stack_id):
        return heatclient(context).stacks.get(stack_id)
    
    def delete_stack(self, context, stack_id):
        return heatclient(context).stacks.delete(stack_id)

    def create_stack(self, context, password=None, **kwargs):
        return heatclient(context, password).stacks.create(**kwargs)


    def preview_stack(self, context, password=None, **kwargs):
        return heatclient(context, password).stacks.preview(**kwargs)

    def validate_template(self, context, **kwargs):
        return heatclient(context).stacks.validate(**kwargs)
    
    def resources_list(self, context, stack_name):
        return heatclient(context).resources.list(stack_name)


    def get_resource(self, context, stack_id, resource_name):
        return heatclient(context).resources.get(stack_id, resource_name)
    
    def events_list(self, context, stack_id):
        return heatclient(context).events.list(stack_id)
    
    def get_event(self, context, stack_id, resource_name, event_id):
        return heatclient(context).events.get(stack_id, resource_name, event_id)
    