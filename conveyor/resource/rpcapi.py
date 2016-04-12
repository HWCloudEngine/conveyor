'''
Created on 

@author: g00357909
'''

import oslo.messaging as messaging
from oslo.config import cfg

from conveyor.common import log as logging
from conveyor import rpc

LOG = logging.getLogger(__name__)

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


    def get_resource_types(self, context):
        LOG.debug("get the types of resources which can be cloned or migrated.")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_types')
    

    def get_resources(self, context, search_opts=None, marker=None, limit=None):
        LOG.debug("get resources filtering by: %s", search_opts)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resources',
                          search_opts=search_opts,
                          marker=marker, limit=limit)
    
       
    def create_plan(self, context, type, resources):
        LOG.debug("create a new plan.")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'create_plan', type=type, resources=resources)
    
    def create_plan_by_template(self, context, template):
        LOG.debug("create plan by template.")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'create_plan_by_template', template=template)

    def get_resource_detail(self, context, resource_type, resource_id):
        LOG.debug("get %s resource details of <%s>.", resource_type, resource_id)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_detail', 
                          resource_type=resource_type,
                          resource_id=resource_id)
    
    def get_resource_detail_from_plan(self, context, plan_id, resource_id):
        LOG.debug("get details of resource <%s> in plan %s", 
                                resource_id, plan_id)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_resource_detail_from_plan', 
                          plan_id=plan_id, 
                          resource_id=resource_id)

    def update_plan(self, context, plan_id, values):
        LOG.debug("update plan: %s", plan_id)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'update_plan', 
                          plan_id=plan_id, values=values)
    
    
    def get_plan_by_id(self, context, plan_id):
        LOG.debug("get plan detail of %s", plan_id)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_plan_by_id', plan_id=plan_id)
    
    
    def get_plans(self, context, search_opts=None):
        LOG.debug("get all plans")
        cctxt = self.client.prepare(version='1.18')
        return cctxt.call(context, 'get_plans', search_opts=search_opts)


    def delete_plan(self, context, plan_id):
        LOG.debug("delete plan : %s", plan_id)
        cctxt = self.client.prepare(version='1.18')
        return cctxt.cast(context, 'delete_plan', plan_id=plan_id)
    
