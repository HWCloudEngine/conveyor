'''
Created on 2016

@author: g00357909
'''

from conveyor.common import log as logging
from conveyor.resource import rpcapi

LOG = logging.getLogger(__name__)


class ResourceAPI(object):
    
    def __init__(self):
        self.resource_rpcapi = rpcapi.ResourceAPI()
        super(ResourceAPI, self).__init__()
          
    def get_resource_types(self, context):
        return self.resource_rpcapi.get_resource_types(context)

    def get_resources(self, context, search_opts=None, marker=None, limit=None):
        return self.resource_rpcapi.get_resources(context, search_opts=search_opts,
                                                  marker=marker, limit=limit)
       
    def create_plan(self, context, type, resources):
        return self.resource_rpcapi.create_plan(context, type, resources)
    
    
    def create_plan_by_template(self, context, template):
        return self.resource_rpcapi.create_plan_by_template(context, template)
    
    def get_resource_detail(self, context, resource_type, resource_id):
        return self.resource_rpcapi.get_resource_detail(context, resource_type, resource_id)
        
    def get_resource_detail_from_plan(self, context, plan_id, resource_id):
        return self.resource_rpcapi.get_resource_detail_from_plan(context, 
                                                            plan_id, resource_id)

    def update_plan(self, context, plan_id, values):
        return self.resource_rpcapi.update_plan(context, plan_id, values)

    def get_plans(self, context, search_opts=None):
        return self.resource_rpcapi.get_plans(context, search_opts=search_opts)
    
    def get_plan_by_id(self, context, plan_id):
        return self.resource_rpcapi.get_plan_by_id(context, plan_id)
    
    def delete_plan(self, context, plan_id):
        return self.resource_rpcapi.delete_plan(context, plan_id)
    
    
    
