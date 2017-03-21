'''
@author: g00357909
'''

import datetime
import copy
import six
from oslo_config import cfg

from oslo_serialization import jsonutils
from oslo_utils import fileutils
from oslo_utils import timeutils
from oslo_log import log as logging
from conveyor.common import plan_status as p_status
from conveyor import exception

from conveyor.db import api as db_api

LOG = logging.getLogger(__name__)


# instance_allowed_search_opts = ['reservation_id', 'name', 'status', 'image', 'flavor',
#                                'tenant_id', 'ip', 'changes-since', 'all_tenants']


class Resource(object):
    """Describes an OpenStack resource."""

    def __init__(self, name, type, id, properties=None, extra_properties=None, parameters=None):
        self.name = name
        self.type = type
        self.id = id or ""
        self.properties = properties or {}
        self.extra_properties = extra_properties or {}
        self.parameters = parameters or {}
        self.extra_properties['id'] = self.id

    def add_parameter(self, name, description, parameter_type='string',
                      constraints=None, default=None):
        data = {
            'type': parameter_type,
            'description': description,
        }

        if default:
            data['default'] = default

        self.parameters[name] = data
        
    def add_property(self, key, value):
        self.properties[key] = value

    def add_extra_property(self, key, value):
        self.extra_properties[key] = value
        
    @property
    def template_resource(self):
        return {
            self.name: {
                'type': self.type,
                'properties': self.properties,
                'extra_properties': self.extra_properties
            }
        }
        
    @property
    def template_parameter(self):
        return self.parameters
    
    def to_dict(self):
        resource = {
                  "id": self.id,
                  "name": self.name,
                  "type": self.type,
                  "properties": self.properties,
                  "extra_properties": self.extra_properties,
                  "parameters": self.parameters
                  }
        return resource
    
    @classmethod
    def from_dict(cls, resource_dict):
        self = cls(resource_dict['name'], 
                   resource_dict['type'], resource_dict['id'], 
                   properties=resource_dict.get('properties'), 
                   extra_properties=resource_dict.get('extra_properties'),
                   parameters=resource_dict.get('parameters'))
        return self
    
    def rebuild_parameter(self, parameters):
        
        def get_params(properties):
            if isinstance(properties, dict) and len(properties) == 1:
                key = properties.keys()[0]
                value = properties[key]
                if key == "get_param":
                    if isinstance(value, six.string_types) and value in parameters.keys():
                        param = parameters[value]
                        self.add_parameter(value, 
                                           param.get('description', ''), 
                                           parameter_type=param.get('type', 'string'),
                                           constraints=param.get('constraints', ''),
                                           default=param.get('default', ''))
                    else:
                        msg = ("Parameter %s is invalid or not found." % value)
                        LOG.error(msg)
                        raise exception.ParameterNotFound(message=msg)
                else:
                    get_params(properties[key])
            elif isinstance(properties, dict):
                for p in properties.values():
                    get_params(p)
            elif isinstance(properties, list):
                for p in properties:
                    get_params(p)
        
        if not isinstance(parameters, dict):
            return
        self.parameters = {}
        get_params(self.properties)
        

class ResourceDependency(object):
    def __init__(self, id, name, name_in_template, type, dependencies = None):
        self.id = id
        self.name = name
        self.name_in_template = name_in_template
        self.type = type
        self.dependencies = dependencies or []

    def add_dependency(self, res_name):
        if res_name not in self.dependencies:
            self.dependencies.append(res_name)
        
    def to_dict(self):
        dep = {
               "id": self.id,
               "name": self.name,
               "type": self.type,
               "name_in_template": self.name_in_template,
               "dependencies": self.dependencies
               }
                
        return dep

    @classmethod
    def from_dict(cls, dep_dict):
        self = cls(dep_dict['id'], 
                   dep_dict['name'], 
                   dep_dict['name_in_template'], 
                   dep_dict['type'],
                   dependencies=dep_dict.get('dependencies'))
        return self


class Plan(object):
    def __init__(self, plan_id, plan_type, project_id, user_id, stack_id=None,
                 created_at=None, updated_at=None, deleted_at=None,
                 expire_at=None, deleted=None, plan_status=None, task_status=None, 
                 original_resources=None, updated_resources=None, 
                 original_dependencies=None, updated_dependencies=None):
        
        self.plan_id = plan_id
        self.plan_type = plan_type
        self.project_id = project_id
        self.user_id = user_id
        self.stack_id = stack_id
        
        self.created_at = created_at or timeutils.utcnow()
        self.updated_at = updated_at or None
        self.deleted_at = deleted_at or None
        self.expire_at = expire_at or \
                         timeutils.utc_after_given_minutes(cfg.CONF.plan_expire_time)
        
        self.deleted = deleted or False
        self.plan_status = plan_status or p_status.INITIATING
        self.task_status = task_status or ''
        
        self.original_resources = original_resources or {}
        self.updated_resources = updated_resources or {}
        self.original_dependencies = original_dependencies or {}
        self.updated_dependencies = updated_dependencies or {}
           

    def rebuild_dependencies(self, is_original=False):
        
        def get_dependencies(properties, deps):
            if isinstance(properties, dict) and len(properties) == 1:
                key = properties.keys()[0]
                value = properties[key]
                if key == "get_resource":
                    if isinstance(value, six.string_types) \
                                and value in resources.keys():
                        deps.append(value)
                elif key == "get_attr":
                    if isinstance(value, list) and len(value) >=1 \
                                and isinstance(value[0], six.string_types) \
                                and value[0] in resources.keys():
                        deps.append(value[0])
                        
                else:
                    get_dependencies(properties[key], deps)
            elif isinstance(properties, dict):
                for p in properties.values():
                    get_dependencies(p, deps)
            elif isinstance(properties, list):
                for p in properties:
                    get_dependencies(p, deps)
                    
        resources = self.original_resources if is_original \
                                    else self.updated_resources
        dependencies = self.original_dependencies if is_original \
                                    else self.updated_dependencies
        
        if not resources:
            return
        
        #if resource has not been modified, there is no need to update dependencies
#         if len(resources) == len(dependencies):
#             is_same = True
#             for res_name in resources.keys():
#                 if res_name not in dependencies.keys():
#                     is_same = False
#                     break
#             if is_same:
#                 return
        #begin to rebuild
        dependencies = {}
        for res in resources.values():
            deps = []
            get_dependencies(res.properties, deps)
            #remove duplicate dependencies
            deps = {}.fromkeys(deps).keys()
            new_dependencies = ResourceDependency(res.id, 
                                                  res.properties.get('name', ''),
                                                  res.name, res.type,
                                                  dependencies=deps)
            dependencies[res.name] = new_dependencies
        
        if is_original:
            self.original_dependencies = dependencies
        else:
            self.updated_dependencies = dependencies
        
    def to_dict(self, detail=True):
        
        def trans_from_obj_dict(object_dict):
            res = {}
            if object_dict and isinstance(object_dict, dict):
                for k, v in object_dict.items():
                    res[k] = v.to_dict()
            return res
            
        plan = {'plan_id': self.plan_id,
                'plan_type': self.plan_type,
                'project_id': self.project_id,
                'user_id': self.user_id,
                'stack_id': self.stack_id,
                'created_at': str(self.created_at) if self.created_at else None,
                'updated_at': str(self.updated_at) if self.updated_at else None,
                'expire_at': str(self.expire_at) if self.expire_at else None,
                'deleted_at': str(self.deleted_at) if self.deleted_at else None,
                'deleted': self.deleted,
                'task_status': self.task_status,
                'plan_status': self.plan_status
                }
        
        if detail:
            plan['original_resources'] = trans_from_obj_dict(self.original_resources)
            plan['updated_resources'] = trans_from_obj_dict(self.updated_resources)
            plan['original_dependencies'] = trans_from_obj_dict(self.original_dependencies)
            plan['updated_dependencies'] = trans_from_obj_dict(self.updated_dependencies)
        
        return plan

    @classmethod
    def from_dict(cls, plan_dict):
        
        def trans_to_obj_dict(r_dict, obj_name):
            obj_dict = {}
            key = 'name'
            if obj_name == 'ResourceDependency':
                key = 'name_in_template'
            for rd in r_dict.values():
                obj_dict[rd[key]] = eval(obj_name).from_dict(rd)
            return obj_dict

        ori_res = plan_dict.get('original_resources')
        ori_dep = plan_dict.get('original_dependencies')
        upd_res = plan_dict.get('updated_resources')
        upd_dep = plan_dict.get('updated_dependencies')
        
        ori_res = trans_to_obj_dict(ori_res, 'Resource') if ori_res else {}
        ori_dep = trans_to_obj_dict(ori_dep, 'ResourceDependency') if ori_dep else {}
        upd_res = trans_to_obj_dict(upd_res, 'Resource') if upd_res else {}
        upd_dep = trans_to_obj_dict(upd_dep, 'ResourceDependency') if upd_dep else {}
        
        plan = {
            'plan_id': '',
            'plan_type': '',
            'project_id': '',
            'user_id': '',
            'stack_id': '',
            'created_at': '',
            'updated_at': '',
            'expire_at': '',
            'deleted_at': '',
            'deleted': '',
            'task_status': '',
            'plan_status': '',
        }
        
        for key in plan.keys():
            plan[key] = plan_dict[key]
            
        plan['original_resources'] = ori_res
        plan['updated_resources'] = upd_res
        plan['original_dependencies'] = ori_dep
        plan['updated_dependencies'] = upd_dep
        
        self = cls(**plan)
        return self

    
class TaskStatus():
    
    """
    creating server_0
    creating volume_0
    ...
    """
    TASKSTATUS = (DEPLOYING, FINISHED, FAILED) \
                = ('deploying', 'finished', 'failed')



def save_plan_to_db(context, plan_file_dir, new_plan):
    
    if isinstance(new_plan, Plan):
        plan = new_plan.to_dict()
    else:
        plan = copy.deepcopy(new_plan)
        
    LOG.debug('Save plan <%s> to database.', plan['plan_id'])
    
    plan.pop('original_dependencies', None)
    plan.pop('updated_dependencies', None)
    
    field_name = ['original_resources', 'updated_resources']
    for name in field_name:
        if plan.get(name):
            full_path = plan_file_dir + plan['plan_id'] + '.' + name
            _write_json_to_file(full_path, plan[name])
            plan[name] = full_path
        else:
            plan[name] = ''
    
    try:
        db_api.plan_create(context, plan)
    except Exception as e:
        LOG.error(unicode(e))
        #Roll back: delete files
        for name in field_name:
            full_path = plan_file_dir + plan['plan_id'] + '.' + name
            fileutils.delete_if_exists(full_path)
            
        raise exception.PlanCreateFailed(message=unicode(e))


def read_plan_from_db(context, plan_id):
    plan_dict = db_api.plan_get(context, plan_id)
    
    field_name = ['original_resources', 'updated_resources']
    for name in field_name:
        if plan_dict.get(name):
            plan_dict[name] = _read_json_from_file(plan_dict[name])
            
    plan_obj = Plan.from_dict(plan_dict)
    
    #rebuild dependencies
    plan_obj.rebuild_dependencies(is_original=True)
    plan_obj.rebuild_dependencies()
    
    return plan_obj.to_dict(), plan_obj


def update_plan_to_db(context, plan_file_dir, plan_id, values):
    
    values.pop('original_dependencies', None)
    values.pop('updated_dependencies', None)
    
    special_fields = ('original_resources', 'updated_resources')
    
    for field in special_fields:
        if field in values.keys() and values[field]:
            full_path = plan_file_dir + plan_id + '.' + field
            _write_json_to_file(full_path, values[field])
            values[field] = full_path
            
    db_api.plan_update(context, plan_id, values)


def _write_json_to_file(full_path, data):
    if not data or not full_path:
        return
    try:
        with fileutils.file_open(full_path, 'w') as fp:
            jsonutils.dump(data, fp, indent=4)
    except Exception as e:
        msg = "Write plan file (%s) failed, %s" % (full_path, unicode(e))
        LOG.error(msg)
        raise exception.PlanFileOperationError(message=msg)

def _read_json_from_file(full_path):
    if not full_path:
        return
    try:
        with fileutils.file_open(full_path, 'r') as fp:
            return jsonutils.load(fp)
    except Exception as e:
        msg = "Read plan file (%s) failed, %s" % (full_path, unicode(e))
        LOG.error(msg)
        raise exception.PlanFileOperationError(message=msg)
    
