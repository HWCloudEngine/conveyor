'''
Created on 2016

@author: g00357909
'''

import copy
from oslo.config import cfg

from conveyor.common import log as logging
from conveyor.resource import rpcapi
from conveyor.common import uuidutils
from conveyor.common import plan_status as p_status
from conveyor.resource import resource

from conveyor.db import api as db_api
from conveyor import heat
from conveyor import exception

LOG = logging.getLogger(__name__)

cfg.CONF.import_opt('plan_file_path', 'conveyor.common.config')
plan_file_dir = cfg.CONF.plan_file_path


class ResourceAPI(object):
    
    def __init__(self):
        self.resource_rpcapi = rpcapi.ResourceAPI()
        super(ResourceAPI, self).__init__()
          
    def get_resource_types(self, context):
        LOG.info("Get resource types.")
        return resource.RESOURCE_TYPES

    def get_resources(self, context, search_opts=None, marker=None, limit=None):
        LOG.info("Get resources filtering by: %s", search_opts)
        return self.resource_rpcapi.get_resources(context, 
                                                  search_opts=search_opts,
                                                  marker=marker, limit=limit)
       
    def create_plan(self, context, type, resources):
        LOG.info("Create a %s plan by resources: %s.", type, resources)
        return self.resource_rpcapi.create_plan(context, type, resources)
    

    def create_plan_by_template(self, context, template):
        LOG.debug("Create plan by specified template.")
        
        #Simply verify basic fields
        standard_template = copy.deepcopy(template)
        expire_time = standard_template.pop('expire_time', '')
        plan_type = standard_template.pop('plan_type', '')
        if plan_type not in ("clone", "migrate"):
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=type)
        
        template_res = standard_template.get('resources')
        if not template_res or not isinstance(template_res, dict):
            msg = "Template format is not correct. \
                    'resources' field must be a dict and not empty."
            LOG.error(msg)
            raise exception.TemplateValidateFailed(message=msg)
        
        #Pop extra properties and verify template by heat 
        for key in standard_template['resources'].keys():
            standard_template['resources'][key].pop('extra_properties', None)
        
        stack_kwargs = dict(stack_name='stack_validate',
                            template=standard_template)
        heat_api = heat.API()
        
        try:
            heat_api.preview_stack(context, **stack_kwargs)
        except Exception as e:
            msg = 'Template validate failed. %s' % unicode(e)
            LOG.error(msg)
            raise exception.TemplateValidateFailed(message=unicode(e))

        #Generate a new plan and build a basic plan.
        plan_id = uuidutils.generate_uuid()
        new_plan = resource.Plan(plan_id, plan_type, 
                                 context.project_id, context.user_id,
                                 expire_at=expire_time,
                                 plan_status=p_status.CREATING)
        
        plan_dict = new_plan.to_dict()
        resource.save_plan_to_db(context, plan_file_dir, plan_dict)
        
        #Extract resources and dependencies from template
        self.resource_rpcapi.build_plan_by_template(context, plan_dict, template)
        
        return plan_dict

    
    def get_resource_detail(self, context, resource_type, resource_id):
        LOG.info("Get %s resource details with id of <%s>.", resource_type, resource_id)
        return self.resource_rpcapi.get_resource_detail(context, 
                                                        resource_type, resource_id)
        
        
    def get_resource_detail_from_plan(self, context, plan_id, 
                                      resource_id, is_original=True):
        
        LOG.info("Get details of %s resource %s of plan <%s>.", 
                 "original" if is_original else "updated", resource_id, plan_id)
        
        return self.resource_rpcapi.get_resource_detail_from_plan(context, plan_id,
                                                                  resource_id,
                                                                  is_original)


    def update_plan(self, context, plan_id, values):

        if not isinstance(values, dict):
            msg = "Update plan failed. 'values' attribute must be a dict."
            LOG.error(msg)
            raise exception.PlanUpdateError(message=msg)
        
        allowed_status = (p_status.INITIATING, p_status.CREATING, p_status.AVAILABLE)
        
        try:
            plan = db_api.plan_get(context, plan_id)
            if 'updated_resources' in values.keys() \
                                    and plan['plan_status'] not in allowed_status:
                msg = ("Plan resources are not allowed to be updated in %s status." 
                       % plan['plan_status'])
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
        except exception.PlanNotFoundInDb:
            LOG.error('Plan <%s> could not be found.', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        
        LOG.info("Update plan <%s> with values: %s", plan_id, values)
        return self.resource_rpcapi.update_plan(context, plan_id, values)
    

    def get_plans(self, context, search_opts=None):
        LOG.info("Get all plans.")
        plan_list = db_api.plan_get_all(context)
        return plan_list

    
    def get_plan_by_id(self, context, plan_id, detail=True):
        LOG.info("Get the plan with id of %s", plan_id)
        return self.resource_rpcapi.get_plan_by_id(context, plan_id, detail=detail)
    
    
    def delete_plan(self, context, plan_id):
        
        allowed_status = (p_status.INITIATING, p_status.CREATING, p_status.AVAILABLE,
                          p_status.ERROR, p_status.FINISHED, p_status.EXPIRED)

        try:
            plan = db_api.plan_get(context, plan_id)
            if plan['plan_status'] not in allowed_status:
                msg = ("Plan isn't allowed to be deleted in %s status." 
                       % plan['plan_status'])
                LOG.error(msg)
                raise exception.PlanDeleteError(message=msg)
        except exception.PlanNotFoundInDb:
            LOG.error('The plan <%s> could not be found.', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        
        LOG.info("Begin to delete plan with id of %s", plan_id)
        return self.resource_rpcapi.delete_plan(context, plan_id)
    
