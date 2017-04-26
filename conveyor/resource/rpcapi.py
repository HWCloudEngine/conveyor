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

import oslo_messaging as messaging
from oslo_config import cfg

from conveyor import rpc


rpcapi_opts = [
    cfg.StrOpt('resource_topic',
               default='conveyor-resource',
               help='The topic resource nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

# rpcapi_cap_opt = cfg.StrOpt('resource',
#         help='Set a version cap for messages sent to resource services. If you '
#              'plan to do a live upgrade from havana to icehouse, you should '
#              'set this option to "icehouse-compat" before beginning the live '
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

    def create_plan(self, context, plan_type, resources):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'create_plan',
                          plan_type=plan_type, resources=resources)

    # has been abolished
    def create_plan_by_template(self, context, template):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'create_plan_by_template',
                          template=template)

    def build_plan_by_template(self, context, plan_dict, template):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'build_plan_by_template',
                          plan_dict=plan_dict, template=template)

    def get_resource_detail(self, context, resource_type, resource_id):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_detail',
                          resource_type=resource_type,
                          resource_id=resource_id)

    def get_resource_detail_from_plan(self, context, plan_id,
                                      resource_id, is_original=True):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_detail_from_plan',
                          plan_id=plan_id,
                          resource_id=resource_id,
                          is_original=is_original)

    def update_plan(self, context, plan_id, values):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'update_plan',
                          plan_id=plan_id, values=values)

    def update_plan_resources(self, context, plan_id, resources):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'update_plan_resources',
                          plan_id=plan_id, resources=resources)

    def get_plan_by_id(self, context, plan_id, detail=True):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_plan_by_id',
                          plan_id=plan_id, detail=detail)

#     def get_plans(self, context, search_opts=None):
#         cctxt = self.client.prepare(version='1.18')
#         return cctxt.call(context, 'get_plans', search_opts=search_opts)

    def delete_plan(self, context, plan_id):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'delete_plan', plan_id=plan_id)

    def force_delete_plan(self, context, plan_id):
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'force_delete_plan', plan_id=plan_id)
