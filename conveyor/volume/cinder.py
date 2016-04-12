# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""
Handles all requests relating to volumes + cinder.
"""

import copy
import sys

from cinderclient import client as cinder_client
from cinderclient import exceptions as cinder_exception
from cinderclient.v1 import client as v1_client
from keystoneclient import exceptions as keystone_exception
from cinderclient import service_catalog
from oslo.config import cfg
from oslo.utils import strutils
import six
import six.moves.urllib.parse as urlparse

from conveyor.common import log as logging

from conveyor import exception
from conveyor.i18n import _
from conveyor.i18n import _LW

cinder_opts = [
    cfg.StrOpt('catalog_info',
            default='volume:cinder:publicURL',
            help='Info to match when looking for cinder in the service '
                 'catalog. Format is: separated values of the form: '
                 '<service_type>:<service_name>:<endpoint_type>',
            deprecated_group='DEFAULT',
            deprecated_name='cinder_catalog_info'),
    cfg.StrOpt('endpoint_template',
               help='Override service catalog lookup with template for cinder '
                    'endpoint e.g. http://localhost:8776/v1/%(project_id)s',
               deprecated_group='DEFAULT',
               deprecated_name='cinder_endpoint_template'),
    cfg.StrOpt('os_region_name',
               help='Region name of this node',
               deprecated_group='DEFAULT',
               deprecated_name='os_region_name'),
    cfg.StrOpt('ca_certificates_file',
               help='Location of ca certificates file to use for cinder '
                    'client requests.',
               deprecated_group='DEFAULT',
               deprecated_name='cinder_ca_certificates_file'),
    cfg.IntOpt('http_retries',
               default=3,
               help='Number of cinderclient retries on failed http calls',
            deprecated_group='DEFAULT',
            deprecated_name='cinder_http_retries'),
    cfg.IntOpt('http_timeout',
               help='HTTP inactivity timeout (in seconds)',
               deprecated_group='DEFAULT',
               deprecated_name='cinder_http_timeout'),
    cfg.BoolOpt('api_insecure',
                default=False,
                help='Allow to perform insecure SSL requests to cinder',
                deprecated_group='DEFAULT',
                deprecated_name='cinder_api_insecure'),
    cfg.BoolOpt('cross_az_attach',
                default=True,
                help='Allow attach between instance and volume in different '
                     'availability zones.',
                deprecated_group='DEFAULT',
                deprecated_name='cinder_cross_az_attach'),
]

CONF = cfg.CONF
# cinder_opts options in the DEFAULT group were deprecated in Juno
CONF.register_opts(cinder_opts, group='cinder')

LOG = logging.getLogger(__name__)

CINDER_URL = None


def cinderclient(context,http_timeout=None):
    global CINDER_URL
    version = get_cinder_client_version(context)
    c = cinder_client.Client(version,
                             context.user_id,
                             context.auth_token,
                             project_id=context.project_id,
                             auth_url=CINDER_URL,
                             insecure=CONF.cinder.api_insecure,
                             retries=CONF.cinder.http_retries,
                             timeout=CONF.cinder.http_timeout if CONF.cinder.http_timeout else http_timeout,
                             cacert=CONF.cinder.ca_certificates_file)
    # noauth extracts user_id:project_id from auth_token
    c.client.auth_token = context.auth_token or '%s:%s' % (context.user_id,
                                                           context.project_id)
    c.client.management_url = CINDER_URL
    return c



def _untranslate_volume_summary_view(context, vol):
    """Maps keys for volumes summary view."""
    d = {}
    d['id'] = vol.id
    d['status'] = vol.status
    d['size'] = vol.size
    d['availability_zone'] = vol.availability_zone
    d['created_at'] = vol.created_at

    # TODO(jdg): The calling code expects attach_time and
    #            mountpoint to be set. When the calling
    #            code is more defensive this can be
    #            removed.
    d['attach_time'] = ""
    d['mountpoint'] = ""

    if vol.attachments:
        att = vol.attachments[0]
        d['attach_status'] = 'attached'
        d['instance_uuid'] = att['server_id']
        d['mountpoint'] = att['device']
    else:
        d['attach_status'] = 'detached'
    # NOTE(dzyu) volume(cinder) v2 API uses 'name' instead of 'display_name',
    # and use 'description' instead of 'display_description' for volume.
    if hasattr(vol, 'display_name'):
        d['display_name'] = vol.display_name
        d['display_description'] = vol.display_description
    else:
        d['display_name'] = vol.name
        d['display_description'] = vol.description
    # TODO(jdg): Information may be lost in this translation
    d['volume_type_id'] = vol.volume_type
    d['snapshot_id'] = vol.snapshot_id
    d['bootable'] = strutils.bool_from_string(vol.bootable)
    d['volume_metadata'] = {}
    for key, value in vol.metadata.items():
        d['volume_metadata'][key] = value

    if hasattr(vol, 'volume_image_metadata'):
        d['volume_image_metadata'] = copy.deepcopy(vol.volume_image_metadata)

    return d

def translate_volume_exception(method):
    """Transforms the exception for the volume but keeps its traceback intact.
    """
    def wrapper(self, ctx, volume_id, *args, **kwargs):
        try:
            res = method(self, ctx, volume_id, *args, **kwargs)
        except (cinder_exception.ClientException,
                keystone_exception.ClientException):
            exc_type, exc_value, exc_trace = sys.exc_info()
            if isinstance(exc_value, (keystone_exception.NotFound,
                                      cinder_exception.NotFound)):
                exc_value = exception.VolumeNotFound(volume_id=volume_id)
            elif isinstance(exc_value, (keystone_exception.BadRequest,
                                        cinder_exception.BadRequest)):
                exc_value = exception.InvalidInput(
                    reason=six.text_type(exc_value))
            raise exc_value, None, exc_trace
        except (cinder_exception.ConnectionError,
                keystone_exception.ConnectionError):
            exc_type, exc_value, exc_trace = sys.exc_info()
            exc_value = exception.CinderConnectionFailed(
                reason=six.text_type(exc_value))
            raise exc_value, None, exc_trace
        return res
    return wrapper


def get_cinder_client_version(context):
    """Parse cinder client version by endpoint url.

    :param context: Nova auth context.
    :return: str value(1 or 2).
    """
    global CINDER_URL
    # FIXME: the cinderclient ServiceCatalog object is mis-named.
    #        It actually contains the entire access blob.
    # Only needed parts of the service catalog are passed in, see
    # nova/context.py.
    compat_catalog = {
        'access': {'serviceCatalog': context.service_catalog or []}
    }
    sc = service_catalog.ServiceCatalog(compat_catalog)
    if CONF.cinder.endpoint_template:
        url = CONF.cinder.endpoint_template % context.to_dict()
    else:
        info = CONF.cinder.catalog_info
        service_type, service_name, endpoint_type = info.split(':')
        # extract the region if set in configuration
        if CONF.cinder.os_region_name:
            attr = 'region'
            filter_value = CONF.cinder.os_region_name
        else:
            attr = None
            filter_value = None
        url = sc.url_for(attr=attr,
                         filter_value=filter_value,
                         service_type=service_type,
                         service_name=service_name,
                         endpoint_type=endpoint_type)
    LOG.debug('Cinderclient connection created using URL: %s', url)

    valid_versions = ['v1', 'v2']
    magic_tuple = urlparse.urlsplit(url)
    scheme, netloc, path, query, frag = magic_tuple
    components = path.split("/")

    for version in valid_versions:
        if version in components[1]:
            version = version[1:]

            if not CINDER_URL and version == '1':
                msg = _LW('Cinder V1 API is deprecated as of the Juno '
                          'release, and Nova is still configured to use it. '
                          'Enable the V2 API in Cinder and set '
                          'cinder_catalog_info in nova.conf to use it.')
                LOG.warn(msg)

            CINDER_URL = url
            return version
    msg = _("Invalid client version, must be one of: %s") % valid_versions
    raise cinder_exception.UnsupportedVersion(msg)


class API(object):
    """API for interacting with the volume manager."""

    @translate_volume_exception
    def get(self, context, volume_id, trans_map=True):
        item = cinderclient(context).volumes.get(volume_id)
        if trans_map:
            return _untranslate_volume_summary_view(context, item)
        return item

    def get_all(self, context, search_opts=None, trans_map=True):
        search_opts = search_opts or {}
        items = cinderclient(context).volumes.list(detailed=True,
                                                   search_opts=search_opts)
        
        if trans_map == False:
            return items

        rval = []

        for item in items:
            rval.append(_untranslate_volume_summary_view(context, item))

        return rval
    
    def create_volume(self, context, size,  name,
               snapshot_id=None,
               description=None, volume_type=None, user_id=None,
               project_id=None, availability_zone=None,
               metadata=None, imageRef=None, scheduler_hints=None):
        
        kwargs = dict(snapshot_id=snapshot_id,
                      description=description,
                      volume_type=volume_type,
                      user_id=context.user_id,
                      project_id=context.project_id,
                      availability_zone=availability_zone,
                      metadata=metadata,
                      imageRef=imageRef,
                      scheduler_hints=scheduler_hints)

        version = get_cinder_client_version(context)
        if version == '1':
            kwargs['display_name'] = name
            kwargs['display_description'] = description
        elif version == '2':
            kwargs['name'] = name
            kwargs['description'] = description
        try:            
            volume = cinderclient(context).volumes.create(size, name, **kwargs)
            
            return _untranslate_volume_summary_view(context, volume)
        except cinder_exception.OverLimit:
            raise exception.QuotaError(overs='volumes')
        except cinder_exception.BadRequest as e:
            raise exception.InvalidInput(reason=unicode(e))

    def migrate_volume_completion(self, context, old_volume_id, new_volume_id,
                                  error=False):
        return cinderclient(context).volumes.migrate_volume_completion(
            old_volume_id, new_volume_id, error)


 
    
    def volume_list(self, context, detailed=True, search_opts=None):
        return cinderclient(context).volumes.list(detailed=detailed,
                                                  search_opts=search_opts)
            
    def get_volume(self, context, volume_id,):
        return cinderclient(context).volumes.get(volume_id)

    def snapshot_list(self, context, detailed=True, search_opts=None):
        return cinderclient(context).volume_snapshots.list(detailed=detailed,
                                                           search_opts=search_opts)
    
    def get_snapshot(self, context, snapshot_id):
        return cinderclient(context).volume_snapshots.get(snapshot_id)
            
    def volume_type_list(self, context, search_opts=None):
        return cinderclient(context).volume_types.list(search_opts=search_opts)
            
    def get_volume_type(self, context, volume_type_id):
        return cinderclient(context).volume_types.get(volume_type_id)
                  
    def qos_specs_list(self, context):
        return cinderclient(context).qos_specs.list()
            
    def get_qos_specs(self, context, qos_specs_id):
        return cinderclient(context).qos_specs.get(qos_specs_id)
            
    def get_qos_associations(self, context, qos_specs_id):
        return cinderclient(context).qos_specs.get_associations(qos_specs_id)

 
