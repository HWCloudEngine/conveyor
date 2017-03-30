'''
Created on 2016

@author: g00357909
'''

import six
import copy
import numbers
from oslo_config import cfg

from oslo_log import log as logging
from conveyor.resource import rpcapi
from oslo_utils import uuidutils
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
        return p_status.RESOURCE_TYPES

    def get_resources(self, context, search_opts=None,
                      marker=None, limit=None):
        LOG.info("Get resources filtering by: %s", search_opts)
        return self.resource_rpcapi.get_resources(context,
                                                  search_opts=search_opts,
                                                  marker=marker, limit=limit)

    def create_plan(self, context, type, resources):
        LOG.info("Create a %s plan by resources: %s.", type, resources)
        return self.resource_rpcapi.create_plan(context, type, resources)

    def create_plan_by_template(self, context, template):
        LOG.debug("Create plan by template. %s", template)

        # Simply verify basic fields
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

        # Pop extra properties and verify template by heat
        for key in standard_template['resources'].keys():
            standard_template['resources'][key].pop('extra_properties', None)

        stack_kwargs = dict(stack_name='stack_validate',
                            template=standard_template)

        is_skip_check = self._is_template_skip_heat_check(standard_template)
        if not is_skip_check:
            heat_api = heat.API()

            try:
                heat_api.preview_stack(context, **stack_kwargs)
            except Exception as e:
                msg = 'Template validate failed. %s' % unicode(e)
                LOG.error(msg)
                raise exception.TemplateValidateFailed(message=unicode(e))

        # Generate a new plan and build a basic plan.
        plan_id = uuidutils.generate_uuid()
        new_plan = resource.Plan(plan_id, plan_type,
                                 context.project_id, context.user_id,
                                 expire_at=expire_time,
                                 plan_status=p_status.CREATING)

        plan_dict = new_plan.to_dict()
        resource.save_plan_to_db(context, plan_file_dir, plan_dict)

        # Extract resources and dependencies from template
        self.resource_rpcapi.build_plan_by_template(context,
                                                    plan_dict,
                                                    template)

        return plan_dict

    def get_resource_detail(self, context, resource_type, resource_id):
        LOG.info("Get %s resource details with id of <%s>.",
                 resource_type, resource_id)
        return self.resource_rpcapi.get_resource_detail(context,
                                                        resource_type,
                                                        resource_id)

    def get_resource_detail_from_plan(self, context, plan_id,
                                      resource_id, is_original=True):
        return self.resource_rpcapi.get_resource_detail_from_plan(context,
                                                                  plan_id,
                                                                  resource_id,
                                                                  is_original)

    def update_plan(self, context, plan_id, values):

        if not isinstance(values, dict):
            msg = "Update plan failed. 'values' attribute must be a dict."
            LOG.error(msg)
            raise exception.PlanUpdateError(message=msg)

        allowed_status = (p_status.INITIATING, p_status.CREATING,
                          p_status.AVAILABLE)

        try:
            plan = db_api.plan_get(context, plan_id)
            if 'updated_resources' in values.keys() \
                    and plan['plan_status'] not in allowed_status:
                msg = ("Plan are not allowed to be updated in %s status."
                       % plan['plan_status'])
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
        except exception.PlanNotFoundInDb:
            LOG.error('Plan <%s> could not be found.', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)

        LOG.info("Update plan <%s> with values: %s", plan_id, values)
        return self.resource_rpcapi.update_plan(context, plan_id, values)

    def update_plan_resources(self, context, plan_id, resources):
        LOG.info("Update resources of plan <%s> with values: %s",
                 plan_id, resources)

        if not isinstance(resources, list):
            msg = "'resources' argument must be a list."
            LOG.error(msg)
            raise exception.PlanUpdateError(message=msg)

        # Verify plan
        allowed_status = (p_status.INITIATING, p_status.CREATING,
                          p_status.AVAILABLE)
        try:
            plan = db_api.plan_get(context, plan_id)
            if plan['plan_status'] not in allowed_status:
                msg = ("Plan are not allowed to be updated in %s status."
                       % plan['plan_status'])
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
        except exception.PlanNotFoundInDb:
            LOG.error('The plan <%s> could not be found.', plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)

        # Verify resources
        for res in resources:
            if not isinstance(res, dict):
                msg = "Every resource to be updated must be a dict."
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

            action = res.get('action')
            if not action or action not in ('add', 'edit', 'delete'):
                msg = "%s action is unsupported." % action
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

            if action == 'add' and ('id' not in res.keys() or
                                    'resource_type' not in res.keys()):
                msg = ("'id' and 'resource_type' of new resource "
                       "must be provided when adding new resources.")
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
            elif action == 'edit' and (len(res) < 2 or
                                       'resource_id' not in res.keys()):
                msg = ("'resource_id' and the fields to be edited "
                       "must be provided when editing resources.")
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
            elif action == 'delete' and 'resource_id' not in res.keys():
                msg = "'resource_id' must be provided when deleting resources."
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

            # Simply parse value.
            for k, v in res.items():
                if v == 'true':
                    res[k] = True
                elif v == 'false':
                    res[k] = False
                elif isinstance(v, six.string_types):
                    try:
                        new_value = eval(v)
                        if type(new_value) in (dict, list, numbers.Number):
                            res[k] = new_value
                    except Exception:
                        pass

        return self.resource_rpcapi.update_plan_resources(context,
                                                          plan_id, resources)

    def get_plans(self, context, search_opts=None):
        LOG.info("Get all plans.")
        plan_list = db_api.plan_get_all(context)
        return plan_list

    def get_plan_by_id(self, context, plan_id, detail=True):
        LOG.info("Get the plan with id of %s", plan_id)
        return self.resource_rpcapi.get_plan_by_id(context, plan_id,
                                                   detail=detail)

    def delete_plan(self, context, plan_id):

        allowed_status = (p_status.INITIATING, p_status.CREATING,
                          p_status.AVAILABLE,
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
        resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                   {'plan_status': p_status.DELETING})
        return self.resource_rpcapi.delete_plan(context, plan_id)

    def force_delete_plan(self, context, plan_id):
        try:
            resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                       {'plan_status': p_status.DELETING})
            rsp = self.resource_rpcapi.force_delete_plan(context, plan_id)
        except Exception as e:
            LOG.error('Force delete plan %(id)s error: %(err)s',
                      {'id': plan_id, 'err': unicode(e)})
            raise
        return rsp

    def _is_template_skip_heat_check(self, template):
        ''' template has resources that heat does not exist,
         template skip heat api check'''

        LOG.debug('Resouce api check template start.')
        RESORCE_TYPE_LIST = ["OS::Neutron::Vip",
                             "OS::Neutron::Listener",
                             "OS::Cinder::VolumeType",
                             "OS::Nova::Flavor"]

        template_res = template.get('resources')
        if not template_res:
            return True

        for res_name, res in template_res.items():
            res_type = res.get('type', None)
            if res_type in RESORCE_TYPE_LIST:
                LOG.debug('Resouce api template has spec type.  %s', res_type)
                return True

        LOG.debug('Resouce api check template end. no spec type')
        return False
