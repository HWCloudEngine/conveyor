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

from oslo_config import cfg
import oslo_messaging as messaging

from conveyor import rpc

rpcapi_opts = [
    cfg.StrOpt('resource_topic',
               default='conveyor-resource',
               help='The topic resource nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

# rpcapi_cap_opt = cfg.StrOpt('resource',
#         help='Set a version cap for messages sent to '
#              'resource services. If you '
#              'plan to do a live upgrade from havana to icehouse, you should '
#              'set this option to "icehouse-compat" '
#              'before beginning the live '
#              'upgrade procedure.')
# CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class ResourceAPI(object):
    '''Client side of the volume rpc API.

    API version history:
        1.0 - Initial version.
    '''

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic=None):
        super(ResourceAPI, self).__init__()
        target = messaging.Target(topic=CONF.resource_topic,
                                  version=self.BASE_RPC_API_VERSION)
        self.client = rpc.get_client(target, '1.23', serializer=None)

    def get_resources(self, context, search_opts=None,
                      marker=None, limit=None):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resources',
                          search_opts=search_opts,
                          marker=marker, limit=limit)

    def build_resources_topo(self, context, plan_id,
                             az_map, search_opt=None):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'build_resources_topo',
                          plan_id=plan_id,
                          availability_zone_map=az_map,
                          search_opts=search_opt)

    def get_resource_detail(self, context, resource_type, resource_id):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_detail',
                          resource_type=resource_type,
                          resource_id=resource_id)

    def list_clone_resources_attribute(self, context, plan_id, attribute):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'list_clone_resources_attribute',
                          plan_id=plan_id,
                          attribute=attribute)

    def build_resources(self, context, resources):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'build_resources', resources=resources)

    def replace_resources(self, context, resources, ori_res, ori_dep):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'replace_resources',
                          resources=resources, updated_res=ori_res,
                          updated_dep=ori_dep)

    def update_resources(self, context, data_copy, resources, ori_res,
                         ori_dep):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'update_resources',
                          data_copy=data_copy,
                          resources=resources, updated_res=ori_res,
                          updated_dep=ori_dep)

    def delete_cloned_resource(self, context, plan_id):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'delete_cloned_resource', plan_id=plan_id)
