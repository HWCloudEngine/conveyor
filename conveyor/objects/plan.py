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

import copy
import six

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

from conveyor.common import plan_status as p_status
from conveyor.common import utils
from conveyor.db import api as db_api
from conveyor import exception
from conveyor.resource import resource

LOG = logging.getLogger(__name__)


class Plan(object):
    def __init__(self, plan_id, plan_type, project_id, user_id, stack_id=None,
                 created_at=None, updated_at=None, deleted_at=None,
                 expire_at=None, deleted=None, plan_status=None,
                 task_status=None, plan_name=None, original_resources=None,
                 updated_resources=None, original_dependencies=None,
                 updated_dependencies=None, sys_clone=False, copy_data=True):

        self.plan_id = plan_id
        self.plan_type = plan_type
        self.plan_name = plan_name
        self.project_id = project_id
        self.user_id = user_id
        self.stack_id = stack_id

        self.created_at = created_at or timeutils.utcnow()
        self.updated_at = updated_at or None
        self.deleted_at = deleted_at or None
        self.expire_at = expire_at or \
            utils.utc_after_given_minutes(cfg.CONF.plan_expire_time)

        self.deleted = deleted or False
        self.plan_status = plan_status or p_status.INITIATING
        self.task_status = task_status or ''
        self.sys_clone = sys_clone
        self.copy_data = copy_data

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
                    if isinstance(value, list) and len(value) >= 1 \
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

        resources = \
            self.original_resources if is_original else self.updated_resources
        dependencies = self.original_dependencies if \
            is_original else self.updated_dependencies

        if not resources:
            return

        dependencies = {}
        for res in resources.values():
            deps = []
            get_dependencies(res.properties, deps)
            # remove duplicate dependencies
            deps = {}.fromkeys(deps).keys()
            new_dependencies = resource.ResourceDependency(
                res.id,
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
                    if isinstance(v, dict):
                        res[k] = v
                    else:
                        res[k] = v.to_dict()
            return res

        plan = {'plan_id': self.plan_id,
                'plan_name': self.plan_name,
                'plan_type': self.plan_type,
                'project_id': self.project_id,
                'user_id': self.user_id,
                'stack_id': self.stack_id,
                'created_at': str(self.created_at) if
                self.created_at else None,
                'updated_at': str(self.updated_at) if
                self.updated_at else None,
                'expire_at': str(self.expire_at) if self.expire_at else None,
                'deleted_at': str(self.deleted_at) if
                self.deleted_at else None,
                'deleted': self.deleted,
                'task_status': self.task_status,
                'plan_status': self.plan_status,
                'sys_clone': self.sys_clone,
                'copy_data': self.copy_data
                }

        if detail:
            plan['original_resources'] = \
                trans_from_obj_dict(self.original_resources)
            plan['updated_resources'] = \
                trans_from_obj_dict(self.updated_resources)
            plan['original_dependencies'] = \
                trans_from_obj_dict(self.original_dependencies)
            plan['updated_dependencies'] = \
                trans_from_obj_dict(self.updated_dependencies)

        return plan

    @classmethod
    def from_dict(cls, plan_dict):

        def trans_to_obj_dict(r_dict, obj_name):
            obj_dict = {}
            key = 'name'
            if obj_name == 'resource.ResourceDependency':
                key = 'name_in_template'
            for rd in r_dict.values():
                obj_dict[rd[key]] = eval(obj_name).from_dict(rd)
            return obj_dict

        ori_res = plan_dict.get('original_resources')
        ori_dep = plan_dict.get('original_dependencies')
        upd_res = plan_dict.get('updated_resources')
        upd_dep = plan_dict.get('updated_dependencies')

        ori_res = trans_to_obj_dict(ori_res,
                                    'resource.Resource') if ori_res else {}
        ori_dep = trans_to_obj_dict(ori_dep,
                                    'resource.ResourceDependency') if \
            ori_dep else {}
        upd_res = trans_to_obj_dict(upd_res,
                                    'resource.Resource') if upd_res else {}
        upd_dep = trans_to_obj_dict(upd_dep, 'resource.ResourceDependency') if \
            upd_dep else {}

        plan = {
            'plan_id': '',
            'plan_name': '',
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


class PlanTemplate(object):

    def __init__(self, plan_id, template, created_at=None,
                 updated_at=None, deleted_at=None, deleted=None):
        self.plan_id = plan_id
        self.template = template or {}
        self.created_at = created_at or timeutils.utcnow()
        self.updated_at = updated_at or None
        self.deleted_at = deleted_at or None
        self.deleted = deleted or False

    def to_dict(self, detail=True):
        template_version = self.template.get('heat_template_version', None)
        if template_version and not isinstance(template_version, str):
            template_version = template_version.strftime('%Y-%m-%d')
            self.template['heat_template_version'] = template_version

        template = {'plan_id': self.plan_id,
                    'template': self.template,
                    'created_at': str(self.created_at) if
                    self.created_at else None,
                    'updated_at': str(self.updated_at) if
                    self.updated_at else None,
                    'deleted_at': str(self.deleted_at) if
                    self.deleted_at else None,
                    'deleted': self.deleted,
                    }

        return template

    @classmethod
    def from_dict(cls, template_dict):

        template = {
                'plan_id': '',
                'template': ''
            }

        for key in template.keys():
            template[key] = template_dict[key]

        self = cls(**template)
        return self


class TaskStatus(object):
    """
    creating server_0
    creating volume_0
    ...
    """
    TASKSTATUS = (DEPLOYING, FINISHED, FAILED) \
               = ('deploying', 'finished', 'failed')


def save_plan_to_db(context, new_plan):

    if isinstance(new_plan, Plan):
        plan = new_plan.to_dict()
    else:
        plan = copy.deepcopy(new_plan)

    LOG.debug('Save plan <%s> to database.', plan['plan_id'])
    try:
        db_api.plan_create(context, plan)
    except Exception as e:
        LOG.error(unicode(e))
        raise exception.PlanCreateFailed(message=unicode(e))


def read_plan_from_db(context, plan_id):
    plan_dict = db_api.plan_get(context, plan_id)
    plan_obj = Plan.from_dict(plan_dict)
    # rebuild dependencies
    plan_obj.rebuild_dependencies(is_original=True)
    plan_obj.rebuild_dependencies()

    return plan_obj.to_dict()


def update_plan_to_db(context, plan_id, values):

    db_api.plan_update(context, plan_id, values)
