# Copyright 2013 IBM Corp.
#
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

"""
Handles all requests to conveyorcaa.
"""
from webob import exc

from oslo_config import cfg
from oslo_log import log as logging

from cinderclient import exceptions as cinderclient_exceptions
from conveyor.conveyorcaa.api import ConveyorcaaClientWrapper
from conveyor import exception
from conveyor.i18n import _LE

CONF = cfg.CONF


LOG = logging.getLogger(__name__)


class API(ConveyorcaaClientWrapper):
    """API for interacting with the volume manager."""

    def get(self, context, volume_id, trans_map=True):

        volume = None
        try:
            volume = self.call('get_volume')
        except exc.HTTPNotFound:
            LOG.error(_LE('Can not find volume %s info'), volume_id)
            raise cinderclient_exceptions.NotFound
        except Exception as e:
            LOG.error(_LE('Query volume %(id)s info error: %(err)s'),
                      {'id': volume_id, 'err': e})
            raise exception.V2vException
        return volume

    def get_all(self, context, search_opts=None, trans_map=True):
        volumes = []
        try:
            volumes = self.call('list_volume')
        except Exception as e:
            LOG.error(_LE('Query all volume info error: %(err)s'),  e)
            raise exception.V2vException
        return volumes

    def create_volume(self, context, size,  name,
                      snapshot_id=None, description=None,
                      volume_type=None, user_id=None,
                      project_id=None, availability_zone=None,
                      metadata=None, imageRef=None, scheduler_hints=None):

        pass

    def migrate_volume_completion(self, context, old_volume_id, new_volume_id,
                                  error=False):
        pass

    def snapshot_list(self, context, detailed=True, search_opts=None):
        pass

    def get_snapshot(self, context, snapshot_id):
        pass

    def volume_type_list(self, context, search_opts=None, trans_map=True):

        type_list = []
        try:
            type_list = self.call('list_volume_type')
        except Exception as e:
            LOG.error(_LE('Query all volume type info error: %(err)s'),  e)
            raise exception.V2vException
        return type_list

    def get_volume_type(self, context, volume_type_id, trans_map=True):

        volume_type = None
        try:
            volume_type = self.call('get_volume_type')
        except exc.HTTPNotFound:
            LOG.error(_LE('Can not find volume type %s info'), volume_type_id)
            raise cinderclient_exceptions.NotFound
        except Exception as e:
            LOG.error(_LE('Query volumetype  %(id)s info error: %(err)s'),
                      {'id': volume_type_id, 'err': e})
            raise exception.V2vException
        return volume_type

    def get_consisgroup(self, context, consisgroup_id):
        pass

    def qos_specs_list(self, context, trans_map=True):
        pass

    def get_qos_specs(self, context, qos_specs_id, trans_map=True):
        pass

    def get_qos_associations(self, context, qos_specs_id):
        pass

    def delete(self, context, volume_id):
        pass

    def set_volume_bootable(self, context, volume_id, flag):
        pass

    def set_volume_shareable(self, context, volume_id, flag):
        pass

    def reset_state(self, context, volume_id, state):
        pass
