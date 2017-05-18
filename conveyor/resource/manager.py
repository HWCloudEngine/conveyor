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

import yaml
import copy
import six
import numbers
import netaddr
import random
from oslo_config import cfg
from oslo_utils import importutils
import oslo_messaging as messaging

from conveyor.common import plan_status as p_status
from oslo_utils import fileutils
from oslo_utils import uuidutils
from oslo_utils import timeutils
from oslo_log import log as logging
from conveyor.db import api as db_api

from conveyor import exception
from conveyor import compute
from conveyor import volume
from conveyor import network
from conveyor import image
from conveyor.conveyorheat.api import api as heat
from conveyor import utils
from conveyor import manager
from conveyor.resource import resource

from conveyor.resource.driver.float_ips import FloatIps
from conveyor.resource.driver.instances import InstanceResource
from conveyor.resource.driver import loadbalance
from conveyor.resource.driver.networks import NetworkResource
from conveyor.resource.driver.secgroup import SecGroup
from conveyor.resource.driver.volumes import VolumeType
from conveyor.resource.driver.volumes import QosResource
from conveyor.resource.driver.volumes import Volume
from conveyor.resource.driver.stacks import StackResource

CONF = cfg.CONF


LOG = logging.getLogger(__name__)
resource_plugins_opts = [
    cfg.StrOpt('resource_driver',
               default='conveyor.resource.plugins.openstack.driver.'
                       'OpenstackDriver',
               help='Driver to connect cloud')
]

CONF.register_opts(resource_plugins_opts)
CONF.import_opt('clear_expired_plan_interval', 'conveyor.common.config')
CONF.import_opt('plan_file_path', 'conveyor.common.config')
CONF.import_group('keystone_authtoken', 'conveyor.common.config')

plan_file_dir = CONF.plan_file_path

_plans = {}


class ResourceManager(manager.Manager):
    """Get detail resource."""

    target = messaging.Target(version='1.18')

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """  ."""
        self.nova_api = compute.API()
        self.cinder_api = volume.API()
        self.neutron_api = network.API()
        self.glance_api = image.API()
        self.heat_api = heat.API()
        self.db_api = db_api
        resource_driver_class = importutils.import_class(CONF.resource_driver)
        self.resource_driver = resource_driver_class()

        # Start periodic task to clear expired plan
        # context = ctxt.get_admin_context()
#         kwargs = {
#             'username': CONF.keystone_authtoken.conveyor_admin_user,
#             'password': CONF.keystone_authtoken.password,
#             'tenant_name': CONF.keystone_authtoken.conveyor_admin_tenant_name,
#             'auth_url': CONF.keystone_authtoken.auth_url,
#             'insecure': True,
#         }
#         cs = kc.Client(**kwargs)
#         cs.authenticate()
#         user_id = cs.auth_ref['user']['id']
#         project_id = cs.auth_ref['token']['tenant']['id']
#         auth_token = cs.auth_ref['token']['id']
#         sc = service_catalog.ServiceCatalog.factory(cs.auth_ref)
#         service_catalog = sc.get_data()
#         context = ctxt.RequestContext(user_id,
#                                      project_id,
#                                      auth_token=auth_token,
#                                      service_catalog=service_catalog)
#         timer = loopingcall.FixedIntervalLoopingCall(self._clear_expired_plan, context)
#         timer.start(interval=CONF.clear_expired_plan_interval)

        super(ResourceManager, self).__init__(service_name="conveyor-resource",
                                              *args, **kwargs)

    def get_resource_detail(self, context, resource_type, resource_id):

        LOG.info("Get %s resource details with id of <%s>.", resource_type, resource_id)

        method_map = {
            "OS::Nova::Server": "self.nova_api.get_server",
            "OS::Nova::KeyPair": "self.nova_api.get_keypair",
            "OS::Nova::Flavor": "self.nova_api.get_flavor",
            "OS::Cinder::Volume": "self.cinder_api.get",
            "OS::Cinder::VolumeType": "self.cinder_api.get_volume_type",
            "OS::Cinder::Qos": "self.cinder_api.get_qos_specs",
            "OS::Neutron::Net": "self.neutron_api.get_network",
            "OS::Neutron::Subnet": "self.neutron_api.get_subnet",
            "OS::Neutron::Router": "self.neutron_api.get_router",
            "OS::Neutron::SecurityGroup": "self.neutron_api.get_security_group",
            "OS::Neutron::FloatingIP": "self.neutron_api.get_floatingip",
            "OS::Neutron::Vip": "self.neutron_api.get_vip",
            "OS::Neutron::Pool": "self.neutron_api.show_pool",
            #"OS::Neutron::Listener": "self.neutron_api.show_listener",
            "OS::Neutron::PoolMember": "self.neutron_api.show_member",
            "OS::Neutron::HealthMonitor": "self.neutron_api.show_health_monitor"
        }

        if resource_type in method_map.keys():
            try:
                res = eval(method_map[resource_type])(context, resource_id)
                if isinstance(res, list) and len(res) == 1:
                    return res[0]
                return res
            except Exception as e:
                msg = "Get %s resource <%s> failed. %s" % \
                            (resource_type, resource_id, unicode(e))
                LOG.error(msg)
                raise exception.ResourceNotFound(message=msg)
        else:
            LOG.error("The resource type %s is unsupported.", resource_type)
            raise exception.ResourceTypeNotSupported(resource_type=resource_type) 

    def get_resources(self, context, search_opts=None, marker=None, limit=None):

        LOG.info("Get resources filtering by: %s", search_opts)

        res_type = search_opts.pop("type", "")
        if not res_type:
            LOG.error("The resource type is empty.")
            raise exception.ResourceTypeNotFound()

        if res_type == "OS::Nova::Server":
            res = self.nova_api.get_all_servers(context,
                                                search_opts=search_opts,
                                                marker=marker, limit=limit)
        elif res_type == "OS::Nova::KeyPair":
            res = self.nova_api.keypair_list(context)
        elif res_type == "OS::Nova::Flavor":
            res = self.nova_api.flavor_list(context)
        elif res_type == "OS::Nova::AvailabilityZone":
            res = self.nova_api.availability_zone_list(context)
        elif res_type == "OS::Cinder::Volume":
            res = self.cinder_api.get_all(context, search_opts=search_opts)
        elif res_type == "OS::Cinder::VolumeType":
            res = self.cinder_api.volume_type_list(context,
                                                   search_opts=search_opts)
        elif res_type == "OS::Cinder::Qos":
            res = self.cinder_api.qos_specs_list(context)
        elif res_type == "OS::Neutron::Net":
            res = self.neutron_api.network_list(context, **search_opts)
        elif res_type == "OS::Neutron::Subnet":
            res = self.neutron_api.subnet_list(context, **search_opts)
        elif res_type == "OS::Neutron::Router":
            res = self.neutron_api.router_list(context, **search_opts)
        elif res_type == "OS::Neutron::SecurityGroup":
            res = self.neutron_api.secgroup_list(context, **search_opts)
        elif res_type == "OS::Neutron::FloatingIP":
            res = self.neutron_api.floatingip_list(context, **search_opts)
        elif res_type == "OS::Neutron::Pool":
            res = self.neutron_api.list_pools(context, **search_opts)
        elif res_type == "OS::Glance::Image":
            opts = {
                'marker': search_opts.pop('marker', None),
                'limit': search_opts.pop('limit', None),
                'page_size': search_opts.pop('page_size', None),
                'sort_key': search_opts.pop('sort_key', None),
                'sort_dir': search_opts.pop('sort_dir', None)
            }
            opts['filters'] = search_opts
            res = self.glance_api.get_all(context, **opts)
        else:
            LOG.error("The resource type %s is unsupported.", res_type)
            raise exception.ResourceTypeNotSupported(resource_type=res_type)

        return res

    def create_plan(self, context, plan_type, resources, plan_name=None):

        if plan_type not in ["clone", "migrate"]:
            msg = "Plan type must be 'clone' or 'migrate'."
            LOG.error(msg)
            raise exception.PlanTypeNotSupported(type=plan_type)

        LOG.info("Begin to create a %s plan by resources: %s.", plan_type, resources)

        instance_ids = []
        volume_ids = []
        network_ids = []
        router_ids = []
        loadbalancer_ids = []
        floatingip_ids = []
        secgroup_ids = []
        stack_ids = []
        pool_ids = []

        for res in resources:
            res_type = res.get('type', '')
            res_id = res.get('id', '')

            if not res_id or not res_type:
                LOG.warn("Unresolved id or type, id(%s), type(%s)", res_id, res_type)
                continue

            if res_type == 'OS::Nova::Server':
                instance_ids.append(res_id)
            elif res_type == 'OS::Cinder::Volume':
                volume_ids.append(res_id)
            elif res_type == 'OS::Neutron::Net':
                network_ids.append(res_id)
            elif res_type == 'OS::Neutron::Router':
                router_ids.append(res_id)
            elif res_type == 'OS::Neutron::LoadBalancer':
                loadbalancer_ids.append(res_id)
            elif res_type == 'OS::Heat::Stack':
                stack_ids.append(res_id)
            elif res_type == 'OS::Neutron::FloatingIP':
                floatingip_ids.append(res_id)
            elif res_type == "OS::Neutron::SecurityGroup":
                secgroup_ids.append(res_id)
            elif res_type == "OS::Neutron::Pool":
                pool_ids.append(res_id)
            else:
                LOG.error("The resource type %s is unsupported.", res_type)
                raise exception.ResourceTypeNotSupported(resource_type=res_type)

        res_num = len(instance_ids) + len(volume_ids) + len(network_ids) \
                    + len(router_ids) + len(secgroup_ids) + len(loadbalancer_ids) \
                    + len(stack_ids) + len(floatingip_ids) + len(pool_ids)
        if 0 == res_num:
            msg = "No valid resources found, please check the resource id and type."
            LOG.error(msg)
            raise exception.ResourceExtractFailed(reason=msg)
        ir = InstanceResource(context)

        if instance_ids:
            ir.extract_instances(instance_ids)

        new_resources = ir.get_collected_resources()
        new_dependencies = ir.get_collected_dependencies()

        # if need generate network resource
        if network_ids:
            nt = NetworkResource(context, collected_resources=new_resources,
                                 collected_dependencies=new_dependencies)
            nt.extract_networks_resource(network_ids)
            new_resources = nt.get_collected_resources()
            new_dependencies = nt.get_collected_dependencies()

        # if need generate floating ips resource
        if floatingip_ids:
            ft = FloatIps(context, collected_resources=new_resources,
                          collected_dependencies=new_dependencies)
            ft.extract_floatingips(floatingip_ids)
            new_resources = ft.get_collected_resources()
            new_dependencies = ft.get_collected_dependencies()

        # if need generate secure group resource
        if secgroup_ids:
            st = SecGroup(context, collected_resources=new_resources,
                          collected_dependencies=new_dependencies)
            st.extract_secgroups(secgroup_ids)
            new_resources = st.get_collected_resources()
            new_dependencies = st.get_collected_dependencies()

        # loadbalance resource create
        if pool_ids:
            lb = loadbalance.LoadbalancePool(context,
                                             collected_resources=new_resources,
                                             collected_dependencies=new_dependencies)
            lb.extract_loadbalancePools(pool_ids)
            new_resources = lb.get_collected_resources()
            new_dependencies = lb.get_collected_dependencies()

        # volume resource create
        if volume_ids:
            vol = Volume(context,
                         collected_resources=new_resources,
                         collected_dependencies=new_dependencies)
            vol.extract_volumes(volume_ids)
            new_resources = vol.get_collected_resources()
            new_dependencies = vol.get_collected_dependencies()

        if stack_ids:
            stack = StackResource(context,
                                  collected_resources=new_resources,
                                  collected_dependencies=new_dependencies)
            stack.extract_stacks(stack_ids)
            new_resources = stack.get_collected_resources()
            new_dependencies = stack.get_collected_dependencies()

        plan_id = uuidutils.generate_uuid()
        if not plan_name:
            plan_name = plan_id
        ori_res = self._actual_id_to_resource_id(new_resources)
        ori_dep = self._actual_id_to_resource_id(new_dependencies)

        new_plan = resource.Plan(plan_id, plan_type, 
                                 context.project_id, 
                                 context.user_id,
                                 plan_name=plan_name,
                                 original_resources=ori_res,
                                 original_dependencies=ori_dep)

        # Resources of migrate plan are not allowed to be modified, 
        # so 'updated fields' are empty.
        if plan_type == "clone":
            new_plan.updated_resources = copy.deepcopy(ori_res)
            new_plan.updated_dependencies = copy.deepcopy(ori_dep)
        # Save to memory.
        _plans[plan_id] = new_plan

        # Save to database.
        plan_dict = new_plan.to_dict()
        resource.save_plan_to_db(context, plan_file_dir, plan_dict)
        LOG.info("Create plan succeed. Plan_id is %s", plan_id)

        return plan_id, plan_dict['original_dependencies']

    def build_plan_by_template(self, context, plan_dict, template):
        LOG.info("Begin to build plan <%s> by template.", plan_dict['plan_id'])

        # extract resources
        plan = resource.Plan.from_dict(plan_dict)
        plan_id = plan.plan_id
        resources = {}
        template_res = template.get('resources')
        for key, value in template_res.items():
            res_id = value.get('extra_properties', {}).get('id', '')
            if not res_id:
                res_id = uuidutils.generate_uuid()
            template_res[key].get('extra_properties', {}).pop('id', '')
            resource_obj = resource.Resource(key,
                                             value.get('type'),
                                             res_id,
                                             properties=value.get('properties'),
                                             extra_properties=value.get('extra_properties'))
            resource_obj.rebuild_parameter(template.get('parameters'))
            resources[key] = resource_obj

        plan.original_resources = resources
        plan.rebuild_dependencies(is_original=True)
        plan.plan_status = p_status.AVAILABLE

        # Resources of migrate plan are not allowed to be modified, 
        # so 'updated fields' are empty.
        if plan.plan_type == "clone":
            plan.updated_resources = copy.deepcopy(resources)
            plan.updated_dependencies = copy.deepcopy(plan.original_dependencies)

        # Save to memory
        _plans[plan_id] = plan

        plan_dict = plan.to_dict()
        update_values = {
            'plan_status': p_status.AVAILABLE,
            'original_resources': plan_dict['original_resources'],
            'updated_resources': plan_dict['updated_resources']
        }
        tpl_full_path = plan_file_dir + plan_id + '.template'

        try:
            # Update to database
            resource.update_plan_to_db(context, plan_file_dir, plan_id, update_values)

            # Save template file
            with open(tpl_full_path, 'w') as fp:
                yaml.safe_dump(template, fp, default_flow_style=False)

            LOG.info("Create plan by template finished. Plan_id is %s, "
                     "and template file has been saved to %s." 
                      % (plan_id, tpl_full_path))
        except Exception as e:
            msg = "Create plan by template failed! %s" % unicode(e)
            LOG.error(msg)
            # Roll back: change plan status to error
            resource.update_plan_to_db(context, plan_file_dir, plan_id, 
                                       {'plan_status': p_status.ERROR})
            raise exception.PlanCreateFailed(message=msg)

    def get_resource_detail_from_plan(self, context, plan_id, 
                                      resource_id, is_original=True):
        LOG.info("Get details of resource %s in plan <%s>. is_original is %d.", 
                                                resource_id, plan_id, is_original)

        # Check whether plan exist. If not found in memory, get plan from db.
        self.get_plan_by_id(context, plan_id)
        plan = _plans.get(plan_id)

        if is_original:
            resource = plan.original_resources.get(resource_id)
        else:
            resource = plan.updated_resources.get(resource_id)

        if not resource:
            msg = "Resource <%s> not found in plan <%s>" % (resource_id,
                                                            plan_id)
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        return resource.to_dict()

    def get_plan_by_id(self, context, plan_id, detail=True):

        LOG.info("Get plan with id of %s", plan_id)

        plan = _plans.get(plan_id)
        if plan:
            return plan.to_dict(detail=detail)
        else:
            LOG.debug("Get plan <%s> from database.", plan_id)
            plan_dict, plan_obj = resource.read_plan_from_db(context, plan_id)
            _plans[plan_id] = plan_obj

            if detail:
                return plan_dict
            else:
                fields = ('original_resources', 'updated_resources', 
                          'original_dependencies', 'updated_dependencies')
                for field in fields:
                    plan_dict.pop(field, None)
                return plan_dict

    def delete_plan(self, context, plan_id):
        @utils.synchronized(plan_id)
        def _lock_do_delete_plan(context, plan_id, ):
            self._delete_plan(context, plan_id)
        _lock_do_delete_plan(context, plan_id)

    def _delete_plan(self, context, plan_id):
        LOG.info("Begin to delete plan with id of %s", plan_id)

        field_name = ['original_resources', 'updated_resources']
        plan = self.get_plan_by_id(context, plan_id)
        if not plan:
            LOG.error('get plan %s failed' % plan_id)
            raise exception.PlanNotFound(plan_id=plan_id)
        resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                   {'plan_status': p_status.DELETING})
        try:
            # Delete template files
            fileutils.delete_if_exists(plan_file_dir + plan_id + '.template')

            # Delete resource files
            for name in field_name:
                full_path = plan_file_dir + plan_id + '.' + name
                fileutils.delete_if_exists(full_path)

        except Exception as e:
            msg = "Delete plan <%s> failed. %s" % (plan_id, unicode(e))
            LOG.error(msg)
            resource.update_plan_to_db(context, plan_file_dir, plan_id, 
                                       {'plan_status': p_status.ERROR_DELETING})
            raise exception.PlanDeleteError(message=msg)

        self.heat_api.clear_table(context, plan['stack_id'], plan_id)

        # Delete plan in memory
        _plans.pop(plan_id, None)

        # Set deleted status in database
        values = {'plan_status': p_status.DELETED, 'deleted': True,
                  'deleted_at': timeutils.utcnow()}
        resource.update_plan_to_db(context, plan_file_dir, plan_id, values)

        LOG.info("Delete plan with id of %s succeed!", plan_id)

    def force_delete_plan(self, context, plan_id):

        _plans.pop(plan_id, None)
        field_name = ['original_resources', 'updated_resources']

        try:
            fileutils.delete_if_exists(plan_file_dir + plan_id + '.template')
            for name in field_name:
                full_path = plan_file_dir + plan_id + '.' + name
                fileutils.delete_if_exists(full_path)
        except Exception as e:
            msg = "Delete plan <%s> failed. %s" % (plan_id, unicode(e))
            LOG.error(msg)
            resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                       {'plan_status':
                                        p_status.ERROR_DELETING})
            raise exception.PlanDeleteError(message=msg)

        values = {'plan_status': p_status.DELETED, 'deleted': True,
                  'deleted_at': timeutils.utcnow()}
        resource.update_plan_to_db(context, plan_file_dir, plan_id, values)

    def update_plan(self, context, plan_id, values):

        @utils.synchronized(plan_id)
        def _lock_do_update_plan(context, plan_id, values):
            self._do_update_plan(context, plan_id, values)
        _lock_do_update_plan(context, plan_id, values)

    def _do_update_plan(self, context, plan_id, values):
        LOG.info("Update plan <%s> with values: %s", plan_id, values)

        allowed_properties = ['task_status', 'plan_status',
                              'stack_id', 'expire_at', 'updated_resources']

        # Verify the keys and values
        for k,v in values.items():
            if k not in allowed_properties:
                msg = ("Update plan failed. %s field "
                       "not found or unsupported to update." % k)
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)
            elif k == 'plan_status' and v not in p_status.PLAN_STATUS:
                msg = "Update plan failed. '%s' plan_status unsupported." % v
                LOG.error(msg)
                raise exception.PlanUpdateError(message=msg)

        # If values contain updated_resources, set update time.
        if 'updated_resources' in values:
            values['updated_at'] = timeutils.utcnow()

        # Update in database
        task_status_to_db = resource.TaskStatus.TASKSTATUS
        values_to_db = copy.deepcopy(values)
        if values_to_db.get('task_status', '') not in task_status_to_db:
            values_to_db.pop('task_status', None)

        if values_to_db:
            resource.update_plan_to_db(context, plan_file_dir, plan_id, values_to_db)

        # Update to memory. If exists, update plan, 
        # else extract updated plan into memory.
        if _plans.get(plan_id):
            plan = _plans[plan_id]

            for key, value in values.items():
                if key == 'updated_resources':
                    updated_resources = {}
                    for k, v in value.items():
                        updated_resources[k] = resource.Resource.from_dict(v)
                    setattr(plan, key, updated_resources)
                    plan.rebuild_dependencies()
                else:
                    setattr(plan, key, value)
        else:
            plan_dict, plan_obj = resource.read_plan_from_db(context, plan_id)
            _plans[plan_id] = plan_obj

        LOG.info("Update plan with id of %s succeed!", plan_id)   

    def _extract_resources(self, context, id,  type, updated_res):
        if type == 'OS::Cinder::VolumeType':
            vtr = VolumeType(context,updated_res)
            resource_ids = [id]
            resources = vtr.extract_volume_types(resource_ids)
            return vtr.get_collected_resources()
        elif type == 'OS::Cinder::Qos':
            vor = QosResource(context,updated_res)
            resources = vor.extract_qos(id)
            return vor.get_collected_resources()

    def update_plan_resources(self, context, plan_id, resources):
        LOG.info("Update resources of plan <%s> with values: %s", plan_id, resources)

        # Get plan object
        plan = _plans.get(plan_id)
        if not plan:
            self.get_plan_by_id(context, plan_id)
            plan = _plans[plan_id]
        updated_res = copy.deepcopy(plan.updated_resources)
        updated_dep = copy.deepcopy(plan.updated_dependencies)
        resources_list = copy.deepcopy(resources)
        # Update resources
        for res in resources:
            if res.get('action') == 'delete':
                #Remind: dep delete and add
                resource_id = res.pop('resource_id', None)
                updated_res.pop(resource_id)
                for key,value in updated_res.items():
                    if resource_id in value.dependencies:
                        msg = 'have resource denpend on the %s resource ,delete failed' %resource_id
                        raise exception.PlanResourcesUpdateError(message=msg) 
                dependencies = updated_dep.get(resource_id).dependencies
                if dependencies:
                    self._remove_org_depends(dependencies, updated_dep, updated_res)
            elif res.get('action') == 'add':
                # Remind: dep delete and add
                LOG.debug('the add resource info is %s' %res)
                resource_id = res.pop('resource_id', None)
                id = res.get('id')
                type = res.get('resource_type')
                self._resource_id_to_actual_id(updated_res)
                updated_res =self._extract_resources(context, id, type, updated_res)
                self._actual_id_to_resource_id(updated_res)
            elif res.get('action') == 'edit':
                self._edit_plan_resource(context, plan, updated_res, updated_dep, res, resources_list)

        # Update to memory
        plan.updated_resources = updated_res
        # plan.updated_resources = self._actual_id_to_resource_id(context, updated_res)
        plan.rebuild_dependencies()

        # Update to database
        updated_resources = {}
        for k, v in updated_res.items():
            updated_resources[k] = v.to_dict()

        resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                   {"updated_resources": updated_resources})

        LOG.info("Update resource of plan <%s> succeed.", plan_id)

    def _edit_plan_resource(self, context, plan, updated_res,
                            updated_dep, resource, resources_list):
        resource.pop('action', None)
        properties = copy.deepcopy(resource)

        resource_id = properties.pop('resource_id', None)
        resource_obj = updated_res.get(resource_id)
        new_res_id = properties.pop('id', None)
        properties.pop('resource_type', None)
        if not resource_id or not resource_obj:
            msg = "%s resource not found." % resource_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        # Validate properties
        res_type = resource_obj.type
        heat_api = heat.API()

        try:
            uncheck_type = ['OS::Neutron::Vip']
            if res_type not in uncheck_type:
                heat_res_type = heat_api.get_resource_type(context, res_type)
                res_properties = heat_res_type.get('properties')
                LOG.debug("Validate the properties to be updated.")
                self._simple_validate_update_properties(properties, res_properties)
        except exception.PlanResourcesUpdateError:
            raise
        except Exception as e:
            LOG.error(unicode(e))
            raise exception.PlanResourcesUpdateError(message=unicode(e))

        def _update_simple_fields(resource_id, properties):
            for k, v in properties.items():
                updated_res[resource_id].properties[k] = v

        simple_handle_type = ['OS::Neutron::Vip']
        #Update resource
        if 'OS::Nova::Server' == res_type:
            allowed_fields = ['user_data', 'metadata']
            for key,value in properties.items():
                if key in allowed_fields:
                    resource_obj.properties[key] = value
                else:
                    msg = ("'%s' field of server is not allowed to update." % key)
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)
        elif res_type in ('OS::Nova::KeyPair'):
            public_key = properties.get('public_key', None)
            if not new_res_id and not public_key:
                msg = ("'id' or 'public_key' must be provided "
                       "when updating keypair resource.")
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            if new_res_id and new_res_id != resource_obj.id:
                ir = InstanceResource(context)
                kp_res = ir.extract_keypairs([new_res_id])[0]
                kp_res.name = resource_id
                updated_res[resource_id] = kp_res
            else:
                resource_obj.id = None

            # Update other fields. 
            _update_simple_fields(resource_id, properties)

        elif 'OS::Neutron::SecurityGroup' == res_type:
            rules = properties.get('rules', None)

            if not new_res_id and not rules:
                msg = ("'id' or 'rules' must be provided "
                       "when updating security group resource.")
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            if new_res_id and new_res_id != resource_obj.id:
                nr = NetworkResource(context)
                sec_res = nr.extract_secgroups([new_res_id])[0]
                sec_res.name = resource_id
                updated_res[resource_id] = sec_res
            else:
                resource_obj.id = None
            #Update other fields. 
            _update_simple_fields(resource_id, properties)

        elif 'OS::Neutron::FloatingIP' == res_type:
            if not new_res_id:
                msg = "'id' must be provided when updating floating ip resource."
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            if new_res_id != resource_obj.id:

                floatingip = self.neutron_api.get_floatingip(context, new_res_id)
                if floatingip.get('port_id'):
                    msg = "FloatingIp <%s> is in use."
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)

                # Extracted floatingip resource.
                self._resource_id_to_actual_id(updated_res)
                nr = NetworkResource(context, collected_resources=updated_res)
                floatingip_res = nr.extract_floatingips([new_res_id])[0]
                floatingip_res.name = resource_id

                # Reserve port_id
                port_id = resource_obj.properties.get('port_id')
                if port_id:
                    floatingip_res.properties['port_id'] = port_id

                # Remove original floatingip resource
                updated_res.pop(resource_obj.id, None)
                self._actual_id_to_resource_id(updated_res)
            else:
                resource_obj.id = None
            # Update other fields. 
            _update_simple_fields(resource_id, properties)

        elif 'OS::Neutron::Port' == res_type:
            self._update_port_resource(context, updated_res, resource)
        elif 'OS::Neutron::Net' == res_type:
            self._update_network_resource(context, updated_res, updated_dep, resource)
        elif 'OS::Neutron::Subnet' == res_type:
            self._update_subnet_resource(context, updated_res, updated_dep, resource, resources_list)
        elif res_type in simple_handle_type:
            _update_simple_fields(resource_id, properties)
        elif 'OS::Cinder::Volume' == res_type:
            org_volume_id = resource_obj.id
            org_dependices = updated_dep.get(resource_id).dependencies
            if new_res_id != org_volume_id:
                self._resource_id_to_actual_id(updated_res)
                vr = Volume(context, updated_res)
                volume_res = vr.extract_volume(new_res_id)
                volume_res.name = resource_id
                volume_res.extra_properties['exist'] = 'true'
                # openstackid:object
                updated_res = vr.get_collected_resources()
                updated_res.pop(org_volume_id, None)
                self._actual_id_to_resource_id(updated_res)
                plan.updated_resources = updated_res
                plan.rebuild_dependencies()
                new_updated_dep = copy.deepcopy(plan.updated_dependencies)
                if org_dependices:
                    self._remove_org_depends(org_dependices,
                                             new_updated_dep, updated_res)
        elif 'OS::Cinder::VolumeType' == res_type:
            org_volume_type_id = resource_obj.id
            org_dependices = updated_dep.get(resource_id).dependencies
            if new_res_id != org_volume_type_id:
                self._resource_id_to_actual_id(updated_res)
                vtr = VolumeType(context, updated_res)
                vt_res = vtr.extract_volume_type(new_res_id)
                vt_res.name = resource_id
                updated_res = vtr.get_collected_resources()
                updated_res.pop(org_volume_type_id, None)
                self._actual_id_to_resource_id(updated_res)
                plan.updated_resources = updated_res
                plan.rebuild_dependencies()
                new_updated_dep = copy.deepcopy(plan.updated_dependencies)
                if org_dependices:
                    self._remove_org_depends(org_dependices,
                                             new_updated_dep, updated_res)
        else:
            msg = "%s resource is unsupported to update." % res_type
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

    def _remove_org_depends(self, org_dependices,
                            new_updated_dep, updated_res):
        org_dep_also_exist = []
        for dep in org_dependices:
            for key, value in new_updated_dep.items():
                if dep in value.dependencies:
                    org_dep_also_exist.append(dep)
                    break
        delete_deps = [item for item in org_dependices if item not in org_dep_also_exist]
        for dep in delete_deps:
            updated_res.pop(dep)
            dependices = new_updated_dep.get(dep).dependencies
            new_updated_dep.pop(dep)
            if dependices:
                self._remove_org_depends(dependices, new_updated_dep, updated_res)

    def _update_port_resource(self, context, updated_res, resource):

        LOG.debug("Update port %s resource with %s.",
                  resource['resource_id'], resource)

        properties = resource
        resource_id = properties.pop('resource_id', None)
        resource_obj = updated_res[resource_id]
        properties.pop('resource_type',None)
        # Only fixed_ips can be updated.
        ips_to_update = properties.pop('fixed_ips')
        if not ips_to_update:
            msg = "Only 'fixed_ips' property is allowed be updated on a port."
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        # Validate the number of ips on a port
        original_ips = resource_obj.properties.get('fixed_ips')
        if len(original_ips) != len(ips_to_update):
            msg = "The number of fixed ips must remain the same."
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        def _get_pools(subnet_id):
            """Get subnet allocation_pools by neutron api."""
            try:
                subnet = self.neutron_api.get_subnet(context, subnet_id)
                return subnet.get('allocation_pools', [])
            except Exception as e:
                msg = "Subnet <%s> not found. %s" % (subnet_id, unicode(e))
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

        # Validate whether ip address matches the subnet.
        for item in ips_to_update:
            ip_address = item.get('ip_address')
            subnet_id = item.get('subnet_id')

            LOG.debug("Check fixed ip: %s", item)

            # subnet_id is required, ip_address is optional
            if not subnet_id:
                msg = "subnet_id must be provided when updating fixed_ips."
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            # If ip_address is provided, validate it.
            if ip_address:
                LOG.debug("Validate ip address %s.", ip_address)
                # Get subnet range from exist subnet resource.
                allocation_pools = []
                if isinstance(subnet_id, dict) and len(subnet_id) == 1:
                    # Only support 'get_param' and 'get_resource'
                    if subnet_id.get('get_param'):
                        sub_param_id = subnet_id['get_param']
                        if isinstance(sub_param_id, six.string_types):
                            subnet_id = resource_obj.parameters\
                                            .get(sub_param_id, {}).get('default')
                            LOG.debug("Get subnet id <%s> from parameter <%s>.", 
                                      subnet_id, sub_param_id)
                            if subnet_id:
                                allocation_pools = _get_pools(subnet_id)
                            else:
                                msg = "%s parameter not found." % sub_param_id
                                LOG.error(msg)
                                raise exception.PlanResourcesUpdateError(message=msg)
                    elif subnet_id.get('get_resource'):
                        sub_res_id = subnet_id['get_resource']
                        if isinstance(sub_res_id, six.string_types) \
                            and updated_res.get(sub_res_id):
                            allocation_pools = updated_res[sub_res_id]\
                                                .properties.get('allocation_pools')
                        else:
                            msg = "%s resource not found." % sub_res_id
                            LOG.error(msg)
                            raise exception.PlanResourcesUpdateError(message=msg)
                elif isinstance(subnet_id, six.string_types):
                    if uuidutils.is_uuid_like(subnet_id):
                        allocation_pools = _get_pools(subnet_id)
                    else:
                        msg = "Subnet id must be uuid."
                        LOG.error(msg)
                        raise exception.PlanResourcesUpdateError(message=msg)

                if not allocation_pools:
                    msg = "Can not found subnet allocation_pools information."
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)

                # Validate whether ip address in ip range.
                ip_valid = False
                for pool in allocation_pools:
                    start = pool.get('start')
                    end = pool.get('end')
                    if isinstance(start, six.string_types) \
                        and isinstance(end, six.string_types) \
                        and netaddr.IPAddress(ip_address) in netaddr.IPRange(start, end):
                        ip_valid = True

                if not ip_valid:
                    msg = ("Ip address doesn't match allocation_pools %s." 
                           % allocation_pools)
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)

            # Begin to update.
            ip_index = ips_to_update.index(item)
            original_ip_item = original_ips[ip_index]
            original_subnet = original_ip_item.get('subnet_id')

            # Update ip_address
            if ip_address:
                original_ips[ip_index]['ip_address'] = ip_address

            # If subnets are the same, only update ip_address if provided.
            if original_subnet == subnet_id:
                pass
            # If subnet_id is from other exist resource, replace directly.        
            elif isinstance(subnet_id, dict) and len(subnet_id) == 1 \
                                and subnet_id.get('get_resource'):
                sub_res_id = subnet_id['get_resource']
                if isinstance(sub_res_id, six.string_types) \
                            and updated_res.get(sub_res_id):
                    original_ips[ip_index]['subnet_id'] = subnet_id
                    LOG.debug("Update ip_address property %s.", original_ips[ip_index])
                else:
                    msg = "%s resource not found." % sub_res_id
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)
            # If subnet_id is a uuid, get resource by neutron driver.
            # If this subnet has been extracted, it won't be extracted again.
            elif uuidutils.is_uuid_like(subnet_id):
                # Replace the keys by actual_id
                LOG.debug("Extract subnet <%s> resource.", subnet_id)

                # Extracted subnet resource.
                self._resource_id_to_actual_id(updated_res)
                nr = NetworkResource(context, collected_resources=updated_res)
                subnet_res = nr.extract_subnets([subnet_id])[0]

                # Restore the keys
                self._actual_id_to_resource_id(updated_res)
                original_ips[ip_index]['subnet_id'] = {'get_resource': subnet_res.name}

                LOG.debug("Update ip_address property %s.", original_ips[ip_index])
            else:
                msg = "subnet_id (%s) is invalid." % subnet_id
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

        # we need to create new port
        resource_obj.id = None
        # Update other fields.
        for k, v in properties.items():
            updated_res[resource_id].properties[k] = v

    def _update_subnet_resource(self, context, updated_res, updated_dep,
                                resource, resources_list):

        LOG.debug("Update subnet %s resource with %s.",
                  resource['resource_id'], resource)

        properties = resource
        new_res_id = properties.pop('id', None)
        resource_id = properties.pop('resource_id', None)
        properties.pop('resource_type',None)
        resource_obj = updated_res[resource_id]
        org_subnet_id = resource_obj.id

        if new_res_id and not uuidutils.is_uuid_like(new_res_id):
            msg = "Subnet id <%s> must be uuid." % new_res_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)
        if new_res_id and new_res_id != org_subnet_id:
            subnet = self.neutron_api.get_subnet(context, new_res_id)
            new_net_id = subnet['network_id']
            org_net_res_id = resource_obj.properties\
                                .get('network_id', {}).get('get_resource')
            org_net_res = updated_res.get(org_net_res_id)
            if not org_net_res:
                msg = "Network resource <%s> not found." % org_net_res_id
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            # Update network and all corresponding subnets
            if org_net_res.id != new_net_id:
                res_to_update = {'id': new_net_id, 'resource_id': org_net_res_id}
                self._update_network_resource(context, updated_res, updated_dep, 
                                              res_to_update, resource_id)

            # Update currect subnet resource.
            self._update_subnet_and_port(context, updated_res, updated_dep, 
                                         resource_id, new_res_id)
        else:
            self._update_org_subnet_info(context, updated_res,
                                      updated_dep, resource_id, resources_list)

        # Update other fields. 
        for k, v in properties.items():
            updated_res[resource_id].properties[k] = v


    def _update_subnet_and_port(self, context, updated_res, 
                                updated_dep, resource_id, subnet_id):

        resource_obj = updated_res[resource_id]
        org_subnet_id = resource_obj.id

        if not uuidutils.is_uuid_like(subnet_id):
            msg = "Subnet id <%s> must be uuid." % subnet_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        if org_subnet_id == subnet_id:
            LOG.info("Subnet <%s> is the same as original subnet. "
                     "Skip updating.", subnet_id)
            return

        # Extracted subnet resource.
        nr = NetworkResource(context)
        subnet_res = nr.extract_subnets([subnet_id])[0]

        # Update subnet info
        subnet_res.name = resource_id
        updated_res[resource_id] = subnet_res

        # Remove fixed ip on all ports corresponding to this subnet.
        # add by liuling
        # need to remove the port_id
        for rid, dep in updated_dep.items():
            if dep.type == "OS::Neutron::Port" and resource_id in dep.dependencies:
                port_res = updated_res.get(rid)
                if not port_res:
                    continue 
                port_res.id = None
                fixed_ips = port_res.properties.get('fixed_ips')

                if not fixed_ips:
                    continue

                for fip in fixed_ips:
                    if fip.get('ip_address') and \
                        fip.get('subnet_id') == {'get_resource': resource_id}:
                        del fip['ip_address']

    def _update_org_net_info(self, context, updated_res,
                             updated_dep, resource_id):
        # set the related resourece id dependencied on net resource_id
        net_update_resource = ["OS::Neutron::Subnet", "OS::Neutron::Port",
                              "OS::Neutron::FloatingIP","OS::Neutron::Router"]
        sub_update_resource = ["OS::Neutron::RouterInterface",
                                  "OS::Neutron::Port"]
        for rid, dep in updated_dep.items():
                if dep.type in net_update_resource\
                   and resource_id in dep.dependencies:
                    net_related_res = updated_res.get(rid)
                    net_related_res.id = None
                    for res_id, dep_object in updated_dep.items():
                        if dep_object.type in sub_update_resource\
                           and rid in dep_object.dependencies:
                            sub_related_res = updated_res.get(res_id)
                            sub_related_res.id = None
        # set the net resourece id
        net_res = updated_res.get(resource_id)
        net_res.id = None

    def _update_org_subnet_info(self, context, updated_res,
                                updated_dep, resource_id, resources_list):
        res_dependencies_key = updated_dep.get(resource_id).dependencies
        for key in res_dependencies_key:
            res_obj = updated_res.get(key)
            if res_obj.type == "OS::Neutron::Net":
                self._update_org_net_info(context, updated_res,
                                          updated_dep, key)
                need_pop_seg = True
                for res in resources_list:
                    if key == res.get('resource_id'):
                        need_pop_seg = False
                        break
                if need_pop_seg:
                    if updated_res[key].properties.get('value_specs').get('provider:segmentation_id'):
                        updated_res[key].properties.get('value_specs').pop('provider:segmentation_id') 

    def _update_network_resource(self, context, updated_res, updated_dep, 
                                 resource, except_subnet=None):

        LOG.debug("Update network %s resource with %s.", 
                  resource['resource_id'], resource)

        properties = resource
        new_res_id = properties.pop('id', None)
        resource_id = properties.pop('resource_id', None)
        properties.pop('resource_type',None) 

        org_net = updated_res[resource_id]
        org_net_id = org_net.id

        if new_res_id and not uuidutils.is_uuid_like(new_res_id):
            msg = "Network id <%s> must be uuid." % new_res_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        if new_res_id and new_res_id != org_net_id:
            #Make sure the number of subnets larger than one.
            net = self.neutron_api.get_network(context, new_res_id)
            subnets = net.get('subnets', [])
            if not subnets:
                msg = "No subnets found in network %s." % new_res_id
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            # Validate whether network exists on a server. 
            self._validate_server_network_duplication(updated_res, 
                                                      resource_id, new_res_id)

            # Extracted network resource.
            nr = NetworkResource(context)
            net_res = nr.extract_nets([new_res_id])[0]

            # Update network resource.
            net_res.name = resource_id
            updated_res[resource_id] = net_res

            # Update corresponding subnet resources.
            for rid, dep in updated_dep.items():
                if dep.type == "OS::Neutron::Subnet" \
                    and resource_id in dep.dependencies:
                    subnet_res = updated_res.get(rid)

                    if not subnet_res or except_subnet == subnet_res.name:
                        continue

                    #Randomly choose a subnet.
                    random_index = random.randint(0, len(subnets)-1)
                    random_sub_id = subnets[random_index]

                    self._update_subnet_and_port(context, updated_res, 
                                                 updated_dep, rid, random_sub_id)
        else:
            # need to modify
            LOG.info("Network <%s> is the same as original network. "
                     "updating the org_net info", org_net_id)
            self._update_org_net_info(context, updated_res,
                                      updated_dep, resource_id)

            if properties.get('value_specs') and \
               not properties.get('value_specs').get('provider:segmentation_id'):
                if updated_res[resource_id].properties.get('value_specs').get('provider:segmentation_id'):
                    updated_res[resource_id].properties.get('value_specs').pop('provider:segmentation_id')
            elif not properties.get('value_specs'):
                if updated_res[resource_id].properties.get('value_specs').get('provider:segmentation_id'):
                    updated_res[resource_id].properties.get('value_specs').pop('provider:segmentation_id')
 
        # Update other fields.
        for k, v in properties.items():
            updated_res[resource_id].properties[k] = v

    def _validate_server_network_duplication(self, updated_res, 
                                             net_res_id_to_update, net_id):

        LOG.debug("Validate whether network exists on a server.")

        for res in updated_res.values():

            if res.type != "OS::Nova::Server":
                continue

            networks = res.properties.get('networks')
            if not networks:
                continue

            exist_nets = []
            need_validate = False

            def _get_param(res, param_id):
                if isinstance(param_id, six.string_types):
                    return res.parameters.get(param_id, {}).get('default')

            def _get_net_id(uuid_or_network):
                net = uuid_or_network
                if uuidutils.is_uuid_like(net):
                    exist_nets.append(net)
                elif isinstance(net, dict) and len(net) == 1:
                    if net.get('get_param'):
                        net_param = _get_param(res, net['get_param'])
                        if net_param and uuidutils.is_uuid_like(net_param):
                            exist_nets.append(net_param)
                    elif net.get('get_resource'):
                        net_res_id = net['get_resource']
                        if net_res_id == net_res_id_to_update:
                            return True
                        elif isinstance(net_res_id, six.string_types) \
                            and updated_res.get(net_res_id):
                            exist_nets.append(updated_res[net_res_id].id)

            for net in networks:
                port_res_id = net.get('port', {}).get('get_resource')
                net_uuid = net.get('uuid', {})   
                network = net.get('network', {})

                if port_res_id:
                    port_res = updated_res.get(port_res_id)

                    if not port_res:
                        continue

                    network_id = port_res.properties.get('network_id')

                    if uuidutils.is_uuid_like(network_id):
                        exist_nets.append(network_id)
                    elif isinstance(network_id, dict) \
                        and len(network_id) == 1:

                        if network_id.get('get_param'):
                            net_param = _get_param(port_res, 
                                                   network_id['get_param'])
                            if uuidutils.is_uuid_like(net_param):
                                exist_nets.append(net_param)
                        elif network_id.get('get_resource'):
                            net_res_id = network_id['get_resource']
                            if net_res_id == net_res_id_to_update:
                                need_validate = True
                            else:
                                net_res = updated_res.get(net_res_id)
                                if net_res:
                                    exist_nets.append(net_res.id)

                if net_uuid:
                    if _get_net_id(net_uuid) == True:
                        need_validate = True

                if network:
                    if _get_net_id(network) == True:
                        need_validate = True

            if need_validate and net_id in exist_nets:
                msg = ("Duplicate networks <%s> found on server <%s>." 
                       % (net_id, res.name))
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

    def _simple_validate_update_properties(self, args, properties):
        """Simply validate properties to be updated."""

        # If properties info not found, return.
        if not isinstance(properties, dict) or len(properties) < 1:
            return

        if not isinstance(args, dict):
            msg = "The type of update properties(%s) is incorrect." % args
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        type_map = {"integer": numbers.Number,
                    "number": numbers.Number,
                    "boolean": bool,
                    "string": six.string_types,
                    "list": list,
                    "map": dict
                    }

        def _validate_type(value, expected_type):
            if isinstance(value, expected_type):
                return True
            elif expected_type == bool:
                return False
            elif expected_type not in (list, dict) \
                and isinstance(value, dict) and len(value) == 1 \
                and (value.keys()[0] in ('get_resource', 'get_param', 'get_attr')):
                return True
            else:
                return False

        for key, value in args.items():
            #Validate whether property exists.
            if key in properties.keys():
                pro = properties[key]
            elif len(properties) == 1 and properties.keys()[0] == '*':
                pro = properties.values()[0]
            else:
                msg = "Unknown property %s." % args
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            # Validate property type.
            expected_type = pro.get('type')
            if isinstance(expected_type, six.string_types):
                expected_type = expected_type.lower()
            if expected_type not in type_map.keys():
                continue

            expected_type = type_map.get(expected_type)

            # Transform special type.
            if expected_type == six.string_types:
                if isinstance(value, numbers.Number):
                    args[key] = value = str(value)
                elif not value:
                    args[key] = value = ''

            # Validate type
            if not _validate_type(value, expected_type):
                msg = ("The type of property (%s: %s) is incorrect (expect %s type)." 
                        % (key, value, expected_type))
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

            # Validate children properties of dict type
            if isinstance(value, dict) and pro.get('schema'):
                self._simple_validate_update_properties(value, pro['schema'])

            # Validate children properties of list type
            if isinstance(value, list) and pro.get('schema') \
                                       and len(pro['schema']) == 1 \
                                       and pro['schema'].keys()[0] == "*":
                child_schema = pro['schema'].values()[0]
                child_type = child_schema.get('type')
                child_type = type_map.get(child_type)
                if child_type == dict and child_schema.get('schema'):
                    for v in value:
                        self._simple_validate_update_properties(v, child_schema['schema'])
                elif child_type not in (list, dict):
                    for v in value:
                        if not _validate_type(v, child_type):
                            msg = "%s is not string type." % v
                            LOG.error(msg)
                            raise exception.PlanResourcesUpdateError(message=msg)

    def _actual_id_to_resource_id(self, res_or_dep):
        new_res = {}
        if isinstance(res_or_dep, dict):
            for v in res_or_dep.values():
                if isinstance(v, resource.Resource):
                    new_res[v.name] = v
                elif isinstance(v, resource.ResourceDependency):
                    new_res[v.name_in_template] = v

        res_or_dep.clear()
        res_or_dep.update(new_res)
        return res_or_dep

    def _resource_id_to_actual_id(self, res_or_dep):
        new_res = {}
        if isinstance(res_or_dep, dict):
            for v in res_or_dep.values():
                new_res[v.id] = v
        res_or_dep.clear()
        res_or_dep.update(new_res)
        return res_or_dep

    def _clear_expired_plan(self, context):
        """
        Search expired plan in database, and detach migrate port.
        """

        LOG.debug("Searching expired plan.")
        # Search expired plan in database.
        exist_expired_plan = False
        plans = self.db_api.plan_get_all(context)
        for plan in plans:
            if self._has_expired(plan):
                exist_expired_plan = True
                plan_id = plan['plan_id']
                tpl_file_path = plan_file_dir + plan_id + '.template'
                LOG.debug('Plan <%s> has expired.', plan_id)
                plan = self.get_plan_by_id(context, plan_id)
                resources = plan.get('updated_resources', {})
                # Detach temporary port
                if plan['plan_status'] not in (p_status.INITIATING):
                    self.resource_driver.reset_resources(context, resources)

                # Change plan status to expired.
                resource.update_plan_to_db(context, plan_file_dir, plan_id,
                                           {'plan_status': p_status.EXPIRED})

        if not exist_expired_plan:
            LOG.debug("No expired plan found.")
        else:
            LOG.debug("Complete to clearing expired plan.")



    def _has_expired(self, plan):
        status = (p_status.INITIATING, p_status.CREATING, p_status.AVAILABLE, 
                  p_status.ERROR, p_status.FINISHED)

        if isinstance(plan, resource.Plan):
            plan_status = plan.plan_status
            expire_at = plan.expire_at
        else:
            plan_status = plan['plan_status']
            expire_at = plan['expire_at']

        if plan_status in status:
            expire_time = timeutils.parse_isotime(str(expire_at))
            if timeutils.is_older_than(expire_time, 0):
                return True

        return False
