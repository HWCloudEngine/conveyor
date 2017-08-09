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
import json
import numbers
import six

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_utils import uuidutils

from conveyor import compute
from conveyor.conveyorheat.api import api as heat
from conveyor.db import api as db_api
from conveyor import exception
from conveyor import heat as original_heat
from conveyor import image
from conveyor import manager
from conveyor import network
from conveyor.resource.driver.float_ips import FloatIps
from conveyor.resource.driver.instances import InstanceResource
from conveyor.resource.driver import loadbalance
from conveyor.resource.driver.networks import NetworkResource
from conveyor.resource.driver.secgroup import SecGroup
from conveyor.resource.driver.stacks import StackResource
from conveyor.resource.driver import volumes
from conveyor.resource import resource
from conveyor import volume

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

PROJECT_CLONE_RESOURCES_TYPE = ("OS::Nova::Server",
                                "OS::Cinder::Volume",
                                "OS::Neutron::Net",
                                "OS::Neutron::SecurityGroup",
                                "OS::Heat::Stack")

AZ_CLONE_RESOURCES_TYPE = ("OS::Nova::Server",)


class ResourceManager(manager.Manager):
    """Get detail resource."""

    target = messaging.Target(version='1.18')

    # How long to wait in seconds before re-issuing a shutdown
    # signal to a instance during power off.  The overall
    # time to wait is set by CONF.shutdown_timeout.
    SHUTDOWN_RETRY_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        """."""
        self.nova_api = compute.API()
        self.cinder_api = volume.API()
        self.neutron_api = network.API()
        self.glance_api = image.API()
        self.heat_api = heat.API()
        self.original_heat_api = original_heat.API()
        self.db_api = db_api

        super(ResourceManager, self).__init__(service_name=
                                              "conveyor-resource",
                                              *args, **kwargs)

    def get_resource_detail(self, context, resource_type, resource_id):

        LOG.info("Get %s resource details with id of <%s>.",
                 resource_type, resource_id)

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
            "OS::Neutron::Port": "self.neutron_api.get_port",
            "OS::Neutron::SecurityGroup":
                "self.neutron_api.get_security_group",
            "OS::Neutron::FloatingIP": "self.neutron_api.get_floatingip",
            "OS::Neutron::Vip": "self.neutron_api.get_vip",
            "OS::Neutron::Pool": "self.neutron_api.show_pool",
            # "OS::Neutron::Listener": "self.neutron_api.show_listener",
            "OS::Neutron::PoolMember": "self.neutron_api.show_member",
            "OS::Neutron::HealthMonitor":
                "self.neutron_api.show_health_monitor",
            "OS::Heat::Stack": "self.original_heat_api.get_stack"
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
            raise exception.ResourceTypeNotSupported(resource_type=
                                                     resource_type)

    def get_resources(self, context, search_opts=None, marker=None,
                      limit=None):

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
        elif res_type == "OS::Heat::Stack":
            res = self.original_heat_api.stack_list(context, **search_opts)
        else:
            LOG.error("The resource type %s is unsupported.", res_type)
            raise exception.ResourceTypeNotSupported(resource_type=res_type)

        return res

    def build_resources_topo(self, context, plan_id,
                             availability_zone_map,
                             search_opts=None):
        # 1. query clone obj from plan
        plan_info = db_api.plan_get(context, plan_id)
        clone_objs = plan_info.get('clone_resources', [])
        # 2. query all clone resources (list all resources)
        reses_map = self._list_clone_resources(context, clone_objs)
        # query all cloned to destination az resources. clone object
        # include resources are the D-value of this two resources
        cloned_resources = db_api.plan_cloned_resource_get(context, plan_id)
        self._clone_object_include_resources(reses_map, cloned_resources)
        # 3. extract clone resources (resources detail and build dependency)
        resources = []
        for res_type in PROJECT_CLONE_RESOURCES_TYPE:
            clone_reses = reses_map.get(res_type, [])
            for clone_res in clone_reses:
                resources.append({'type': res_type,
                                  'id': clone_res.get('id')})
        original_resources, original_dep = \
            self._build_reources_topo(context, resources)
        self._add_stack_resources_to_original_resources(original_resources)
        # 4. query already cloned resources
        topo_result = []
        for src_az, des_az in availability_zone_map.items():
            az_original_resources = \
                self._get_resources_by_az(original_resources,
                                          original_dep,
                                          src_az)

            az_cloned_resources = \
                db_api.plan_cloned_resource_get(context, plan_id,
                                                availability_zone=des_az)
            az_cloned_deps = []
            for az_cloned_resource in az_cloned_resources:
                az_cloned_dep = az_cloned_resource.get('dependencies', [])
                # cloning include the same resources,
                # only dependencies different in two clones,
                # so save same resources in two times(eg,
                # save [{vm0, dependencies[vo1]}] in first clone,
                # save [{vm0, dependencies[vo2]}] in second clone.
                # as result, add info to az_cloned_deps must combine
                # the same resources info like as
                # [{vm0, dependencies[vo1,vo2]}]
                self._combine_resources(az_cloned_deps, az_cloned_dep)
            # 5. calculate increment resources
            az_topo_result = self._calculate_increment_resources(
                                            az_original_resources,
                                            az_cloned_deps)
            self._add_topo_items(topo_result, az_topo_result)
        # 6. calculate non-az resources increment
        non_az_original_reses = \
            self._get_resources_by_az(original_resources,
                                      original_dep, 'non-az')
        non_az_cloned_resources = \
            db_api.plan_cloned_resource_get(context, plan_id,
                                            availability_zone='non-az')
        non_az_cloned_deps = []
        for non_az_cloned_resource in non_az_cloned_resources:
            non_az_cloned_dep = non_az_cloned_resource.get('dependencies', [])
            self._combine_resources(non_az_cloned_deps, non_az_cloned_dep)
        non_az_topo_result = self._calculate_increment_resources(
                                        non_az_original_reses,
                                        non_az_cloned_deps)
        self._add_topo_items(topo_result, non_az_topo_result)
        return topo_result

    def build_resources(self, context, resources):
        return self._build_reources_topo(context, resources)

    def _build_reources_topo(self, context, resources):
        LOG.error('Resource start build topo %s', resources)

        instance_ids = []
        volume_ids = []
        network_ids = []
        router_ids = []
        loadbalancer_ids = []
        floatingip_ids = []
        secgroup_ids = []
        stack_ids = []
        pool_ids = []
        port_ids = []

        for res in resources:
            res_type = res.get('type', '')
            res_id = res.get('id', '')

            if not res_id or not res_type:
                LOG.warn("Unresolved id or type, id(%s), type(%s)", res_id,
                         res_type)
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
            elif res_type == "OS::Neutron::Port":
                port_ids.append(res_id)
            else:
                LOG.error("The resource type %s is unsupported.", res_type)
#                raise exception.ResourceTypeNotSupported(resource_type=
#                                                         res_type)

        res_num = len(instance_ids) + len(volume_ids) + len(network_ids) + \
                  len(router_ids) + len(secgroup_ids) + \
                  len(loadbalancer_ids) + len(stack_ids) + \
                  len(floatingip_ids) + len(pool_ids)
        if 0 == res_num:
            msg = "No valid resources found, please check " \
                  "the resource id and type."
            LOG.error(msg)
            raise exception.ResourceExtractFailed(reason=msg)

        # get all resources in stacks
        stack_resources = []
        if stack_ids and res_num > len(stack_ids):
            stack_resources = self._get_all_resources_by_stacks(context,
                                                                stack_ids)

        ir = InstanceResource(context)
        if instance_ids:
            # 1.remove server which in stack resources
            instance_ids = self._fliter_resources_by_stack(stack_resources,
                                                           instance_ids)
            ir.extract_instances(instance_ids)

        new_resources = ir.get_collected_resources()
        new_dependencies = ir.get_collected_dependencies()

        # if need generate network resource
        if network_ids:
            # remove server which in stack resources
            network_ids = self._fliter_resources_by_stack(stack_resources,
                                                          network_ids)
            nt = NetworkResource(context, collected_resources=new_resources,
                                 collected_dependencies=new_dependencies)
            nt.extract_networks_resource(network_ids)
            new_resources = nt.get_collected_resources()
            new_dependencies = nt.get_collected_dependencies()

        # if need generate floating ips resource
        if floatingip_ids:
            # remove server which in stack resources
            floatingip_ids = self._fliter_resources_by_stack(stack_resources,
                                                             floatingip_ids)
            ft = FloatIps(context, collected_resources=new_resources,
                          collected_dependencies=new_dependencies)
            ft.extract_floatingips(floatingip_ids)
            new_resources = ft.get_collected_resources()
            new_dependencies = ft.get_collected_dependencies()

        # if need generate secure group resource
        if secgroup_ids:
            # remove server which in stack resources
            secgroup_ids = self._fliter_resources_by_stack(stack_resources,
                                                           secgroup_ids)
            st = SecGroup(context, collected_resources=new_resources,
                          collected_dependencies=new_dependencies)
            st.extract_secgroups(secgroup_ids)
            new_resources = st.get_collected_resources()
            new_dependencies = st.get_collected_dependencies()

        # loadbalance resource create
        if pool_ids:
            # remove server which in stack resources
            pool_ids = self._fliter_resources_by_stack(stack_resources,
                                                       pool_ids)
            lb = loadbalance.LoadbalancePool(context,
                                             collected_resources=
                                             new_resources,
                                             collected_dependencies=
                                             new_dependencies)
            lb.extract_loadbalancePools(pool_ids)
            new_resources = lb.get_collected_resources()
            new_dependencies = lb.get_collected_dependencies()

        # volume resource create
        if volume_ids:
            # remove server which in stack resources
            volume_ids = self._fliter_resources_by_stack(stack_resources,
                                                         volume_ids)
            vol = volumes.Volume(context,
                                 collected_resources=new_resources,
                                 collected_dependencies=new_dependencies)
            vol.extract_volumes(volume_ids)
            new_resources = vol.get_collected_resources()
            new_dependencies = vol.get_collected_dependencies()

        if port_ids:
            port_ids = self._fliter_resources_by_stack(stack_resources,
                                                       port_ids)
            pt = NetworkResource(context, collected_resources=new_resources,
                                 collected_dependencies=new_dependencies)
            pt.extract_ports(port_ids)
            new_resources = pt.get_collected_resources()
            new_dependencies = pt.get_collected_dependencies()

        if stack_ids:
            stack = StackResource(context,
                                  collected_resources=new_resources,
                                  collected_dependencies=new_dependencies)
            stack.extract_stacks(stack_ids)
            new_resources = stack.get_collected_resources()
            new_dependencies = stack.get_collected_dependencies()

        ori_res = self._actual_id_to_resource_id(new_resources)
        ori_dep = self._actual_id_to_resource_id(new_dependencies)
        return ori_res, ori_dep

    def list_clone_resources_attribute(self, context, plan_id, attribute):
        plan_info = db_api.plan_get(context, plan_id)
        clone_objs = plan_info.get('clone_resources', [])

        # if clone obj is only az, return it
        if len(clone_objs) == 1:
            obj_type = clone_objs[0].get('obj_type')
            if obj_type == 'availability_zone' and \
                            attribute == 'availability_zone':
                return [clone_objs[0].get('obj_id')]
        # query clone all resources of clone object
        clone_resources = self._list_clone_resources(context, clone_objs)
        # query all cloned to destination az resources. clone object
        # include resources are the D-value of this two resources
        cloned_resources = db_api.plan_cloned_resource_get(context, plan_id)
        self._clone_object_include_resources(clone_resources, cloned_resources)

        attribute_list = []
        if clone_resources:
            for reses in clone_resources.values():
                for res in reses:
                    value = res.get(attribute, '')
                    if value:
                        attribute_list.append(value)
        # remove duplicate attribute value
        attribute_list = {}.fromkeys(attribute_list).keys()
        return attribute_list

    def _actual_id_to_resource_id(self, res_or_dep):
        new_res = {}
        if isinstance(res_or_dep, dict):
            for v in res_or_dep.values():
                if isinstance(v, resource.Resource):
                    new_res[v.name] = v.to_dict()
                elif isinstance(v, resource.ResourceDependency):
                    new_res[v.name] = v.to_dict()

        res_or_dep.clear()
        res_or_dep.update(new_res)
        return res_or_dep

    def _resource_id_to_actual_id(self, res_or_dep):
        new_res = {}
        if isinstance(res_or_dep, dict):
            for v in res_or_dep.values():
                new_res[v['id']] = v
        res_or_dep.clear()
        res_or_dep.update(new_res)
        return res_or_dep

    def _get_all_resources_by_stacks(self, context, stacks):
        stack_resources = []
        for stack in stacks:
            kwargs = {}
            kwargs['nested_depth'] = CONF.heat_nested_depth
            r_res_list = self.original_heat_api.resources_list(context,
                                                               stack,
                                                               **kwargs)
            if not r_res_list:
                continue
            for r_res in r_res_list:
                r_id = r_res.physical_resource_id
                if not r_id:
                    continue
                stack_resources.append(r_id)
        return stack_resources

    def _fliter_resources_by_stack(self, stack_resources, resouces):
        """remove resource in resources, which in stack_reosurces"""
        res_list = []
        for res in resouces:
            if res not in stack_resources:
                res_list.append(res)
        return res_list

    def _list_clone_resources(self, context, clone_objs):

        if not clone_objs:
            return

        clone_res_map = {}
        for obj in clone_objs:
            obj_id = obj.get('obj_id')
            obj_type = obj.get('obj_type')
            if obj_type == 'project':
                clone_res = self._list_project_resources(context, obj_id)
            elif obj_type == 'availability_zone':
                clone_res = self._list_availability_zone_resources(context,
                                                                   obj_id)
            elif obj_type == 'OS::Heat::Stack':
                clone_res = self._list_stack_resources(context, obj_id)
            else:
                reses = []
                res = self.get_resource_detail(context, obj_type, obj_id)
                reses.append(res)
                clone_res = {obj_type: reses}
            # if clone_res_map has updated one type resources,
            # then add the same type resources to the type resources
            # list, cloud not clone_res_map.update to recover already
            # exist one type resources
            for c_key, c_res in clone_res.items():
                if c_key in clone_res_map.keys():
                    clone_res_map[c_key].extend(c_res)
                else:
                    clone_res_map.update({c_key: c_res})
        return clone_res_map

    def _list_project_resources(self, context, project_id):

        search_opts = {}
        search_opts['project_id'] = project_id
        search_opts['tenant_id'] = project_id
        project_resources_map = {}

        for res_type in PROJECT_CLONE_RESOURCES_TYPE:
            search_opts['type'] = res_type
            reses = self.get_resources(context, search_opts=search_opts)
            project_resources_map[res_type] = reses
        return project_resources_map

    def _list_availability_zone_resources(self, context, availability_zone):

        search_opts = {}
        search_opts['availability_zone'] = availability_zone
        az_resources_map = {}

        for res_type in AZ_CLONE_RESOURCES_TYPE:
            search_opts['type'] = res_type
            reses = self.get_resources(context, search_opts=search_opts)
            az_resources_map[res_type] = reses
        return az_resources_map

    def _list_stack_resources(self, context, stack_id):
        # query resources in stack
        stack_reses = self.original_heat_api.resources_list(context, stack_id)
        clone_reses_map = {}
        for stack_res in stack_reses:
            res_type = stack_res.resource_type
            res_id = stack_res.physical_resource_id
            clone_res = self.get_resource_detail(context, res_type, res_id)
            if res_type in clone_reses_map.keys():
                clone_reses_map[res_type].append(clone_res)
            else:
                clone_reses = []
                clone_reses.append(clone_res)
                clone_reses_map[res_type] = clone_reses
        # query stack information
        stack_info = self.get_resource_detail(context,
                                              'OS::Heat::Stack',
                                              stack_id)
        clone_reses_map['OS::Heat::Stack'] = [stack_info]
        return clone_reses_map

    def _get_resources_by_az(self, resources, dependencies, availability_zone):
        az_resources = []
        if not resources:
            return az_resources

        # add dependencies resource to az_resources
        def _add_dependencies(depend):
            deps = depend.get('dependencies', [])
            if not deps:
                return
            for dep in deps:
                s = dependencies.get(dep.get("name"))
                flag, rs = \
                    self._is_resource_exist(s.get('id', ''), az_resources)
                if not flag:
                    a_s = copy.deepcopy(s)
                    az_resources.append(a_s)
                    _add_dependencies(s)

        for r_n, res in resources.items():
            properties = res.get('properties', {})
            az = properties.get('availability_zone', 'non-az')
            res_type = res.get('type', '')
            az_list = []
            if 'OS::Heat::Stack' == res_type:
                stack_temp = res.get('properties', {}).get('template', {})
                p_dict = json.loads(stack_temp)
                stack_res = p_dict.get('resources', {})
                az_list = self._get_stack_resources_az_list(stack_res)
            if az == availability_zone or availability_zone in az_list:
                depend = dependencies.get(r_n, None)
                if depend:
                    flag, rs = \
                        self._is_resource_exist(depend.get('id', ''),
                                                az_resources)
                    if not flag:
                        a_dep = copy.deepcopy(depend)
                        az_resources.append(a_dep)
                        _add_dependencies(depend)
        return az_resources

    def _calculate_increment_resources(self, original_resources,
                                       cloned_resources):
        """Returns original_resources list after setting
           cloned resources as is_clone is true, and other is false

        :param original_resources: list<resource.ResourceDenpendency.dict()>
        :param cloned_resources: list<resource.ResourceDenpendency.dict()>

        :return: resources of all original_resources when setting is_cloned.
        """
        ors_cloned = []
        ors_new = []
        result = []
        for ors in original_resources:
            ors_id = ors.get('id')
            ors_deps = ors.get('dependencies', [])
            flag, cls_res = \
                self._is_resource_exist(ors_id, cloned_resources)
            if flag:
                ors['is_cloned'] = True
                ors_cloned.append(ors)
                cls_res_deps = cls_res.get('dependencies', [])
                for ors_dep in ors_deps:
                    dep_id = ors_dep.get('id')
                    d_flag, d_res = \
                        self._is_resource_exist(dep_id, cls_res_deps)
                    if d_flag:
                        ors_dep['is_cloned'] = True
                    else:
                        ors_dep['is_cloned'] = False
            else:
                ors['is_cloned'] = False
                for ors_dep in ors_deps:
                    ors_dep['is_cloned'] = False
                ors_new.append(ors)

        result.extend(ors_new)
        result.extend(ors_cloned)
        return result

    def _add_topo_items(self, topo_list, add_datas):
        """insert add_datas to topo_list, if not exist"""
        add_temp = []
        if not add_datas:
            return
        if not topo_list:
            topo_list.extend(add_datas)
            return
        for data in add_datas:
            data_id = data.get('id', '')
            flag = True
            for topo_item in topo_list:
                item_id = topo_item.get('id', '')
                # if add data already exist, is_cloned value
                # is two data value or
                if data_id == item_id:
                    flag = False
                    data_cloned = data.get('is_cloned', False)
                    item_cloned = topo_item.get('is_cloned', False)
                    topo_item['is_cloned'] = data_cloned or item_cloned
                    break
            if flag:
                add_temp.append(data)
        topo_list.extend(add_temp)

    def _combine_resources(self, resources_list, add_resources):
        """
        if item of add_resources has existed in resources_list,
           only combine dependencies of this item, else add item
           to resources_list
        """
        temp_add = []
        if not add_resources:
            return
        if not resources_list:
            resources_list.extend(add_resources)
        for add_res in add_resources:
            flag = True
            add_res_id = add_res.get('id', '')
            for exist_res in resources_list:
                exist_res_id = exist_res.get('id', '')
                if add_res_id == exist_res_id:
                    flag = False
                    add_res_deps = add_res.get('dependencies', [])
                    exist_res_deps = exist_res.get('dependencies', [])
                    temp_deps = []
                    for dep in add_res_deps:
                        dep_id = dep.get('id', None)
                        is_est, s_dep = \
                            self._is_resource_exist(dep_id, exist_res_deps)
                        if not is_est:
                            temp_deps.append(dep)
                    # combine dependencies of item
                    if temp_deps:
                        exist_res_deps.extend(temp_deps)
                    break
            # add item to resources_list after
            if flag:
                temp_add.append(add_res)
        resources_list.extend(temp_add)

    def _build_destination_cloned_resources_dependencies(self, relations,
                                                         dependencies):
        """
        Cloned to destination az resources only save relation,
        their dependencies rebuild as source az resources
        """
        def _get_relation(res_id, relations):
            for rel in relations:
                rel_src_id = rel.get('src_resource_id', '')
                if rel_src_id == res_id:
                    return rel
            return None

        def _get_dependency(dep_id, dependencies):
            for dep in dependencies:
                d_id = dep.get('id', None)
                if dep_id == d_id:
                    return dep
            return None
        new_deps = []
        # relations have all destination az cloned resources
        for relation in relations:
            des_id = relation.get('des_resource_id', '')
            src_id = relation.get('src_resource_id', '')
            dep = _get_dependency(src_id, dependencies)
            d_deps = []
            if dep:
                deps = dep.get('dependencies', [])
                # if source resource has dependency list,
                # change dependency id as its destination resource id,
                # and add dependency list to destination resource
                if deps:
                    for n_dep in deps:
                        n_dep_id = n_dep.get('id', None)
                        n_rel = _get_relation(n_dep_id, relations)
                        if n_rel:
                            n_new_dep = copy.deepcopy(n_dep)
                            n_new_dep['id'] = n_rel.get('des_resource_id', '')
                        else:
                            n_new_dep = copy.deepcopy(n_dep)
                        d_deps.append(n_new_dep)
            new_dep = {'id': des_id, 'dependencies': d_deps}
            new_deps.append(new_dep)
        return new_deps

    def _clone_object_include_resources(self, clone_resources,
                                        cloned_resources):
        """remove conveyor cloned resources in this cloning resources list"""
        if not cloned_resources:
            return
        cloned_resources_ids = []
        # save all cloned resources to cloned_resources_ids
        for cloned_resource in cloned_resources:
            relations = cloned_resource.get('relation', [])
            for relation in relations:
                des_id = relation.get('des_resource_id', None)
                if des_id:
                    cloned_resources_ids.append(des_id)
        # remove all cloned to destination az resources in clone_resources
        for r_type, clone_reses in clone_resources.items():
            for clone_res in clone_reses[:]:
                res_id = clone_res.get('id', '')
                if res_id in cloned_resources_ids:
                    clone_reses.remove(clone_res)

    def _add_stack_resources_to_original_resources(self, origial_resources):
        """if original resources include stack, add resources in stack to
           origial_resources
           """
        stack_resources = {}
        for res_key, res in origial_resources.items():
            res_type = res.get('type', '')
            if 'OS::Heat::Stack' == res_type:
                stack_temp = res.get('properties', {}).get('template', {})
                p_dict = json.loads(stack_temp)
                stack_res = p_dict.get('resources', {})
                stack_resources.update(stack_res)
        origial_resources.update(stack_resources)

    def _get_stack_resources_az_list(self, stack_resources):
        """list all az of stack resources"""
        az_list = []
        for stack_res in stack_resources.values():
            properties = stack_res.get('properties', {})
            az = properties.get('availability_zone', None)
            if az:
                az_list.append(az)
        return az_list

    def _is_resource_exist(self, res_id, cloned_resources):
        if not cloned_resources:
            return False, None
        for res in cloned_resources:
            if res.get('id') == res_id:
                return True, res
        return False, None

    def delete_cloned_resource(self, context, plan_id):
        try:
            plan = db_api.plan_get(context, plan_id)
            self.heat_api.clear_resource(context, plan['stack_id'], plan_id)
        except Exception as e:
            msg = "Delete plan resource <%s> failed. %s" % \
                  (plan_id, unicode(e))
            LOG.error(msg)
            raise exception.PlanDeleteError(message=msg)

    def replace_resources(self, context, resources, updated_res,
                          updated_dep):
        LOG.info("replace resources with values: %s", resources)
        resources_list = copy.deepcopy(resources)
        for res in resources:
            self._replace_plan_resource(context, updated_res,
                                        updated_dep, res, resources_list)
        # new_updated_dep = self.build_dependencies(updated_res)
        # # # Update to database
        # updated_resources = {}
        # for k, v in updated_res.items():
        #     updated_resources[k] = v.to_dict()

        # plan_cls.update_plan_to_db(context, plan_id,
        #                            {"updated_resources": updated_resources})
        LOG.info("replace resource succeed.")
        return updated_res, updated_dep

    def update_resources(self, context, data_copy, resources, updated_res,
                          updated_dep):
        LOG.info("update resources with values: %s", resources)
        resources_list = copy.deepcopy(resources)
        for res in resources:
            self._update_plan_resource(context, data_copy, updated_res,
                                       updated_dep, res, resources_list)
        # new_updated_dep = self.build_dependencies(updated_res)
        # # Update to database
        # updated_resources = {}
        # for k, v in updated_res.items():
        #     updated_resources[k] = v.to_dict()
        LOG.info("update resource succeed.")
        return updated_res, updated_dep

    def _update_plan_resource(self, context, data_copy, updated_res,
                              updated_dep, res, resources_list):
        properties = copy.deepcopy(res)
        resource_id = properties.pop('resource_id', None)
        res_type = properties.pop('resource_type', None)
        d_copy = properties.pop('copy_data', True)
        rules = properties.pop('rules', [])
        resource_obj = None
        resource_name = None
        # if the new res exist in extracted resource, then return
        for i_key, i_value in updated_res.items():
            ext_id = i_value['extra_properties']['id']
            if resource_id == ext_id:
                resource_obj = updated_res.get(i_key)
                resource_name = i_key
                break
        if not resource_id or not resource_obj:
            # get resources from stack
            for r_key, r_value in updated_res.items():
                r_type = r_value.get('type')
                if r_type == 'OS::Heat::Stack':
                    template = r_value['properties'].get('template')
                    template_dict = json.loads(template)
                    s_resource = template_dict.get('resources', {})
                    for s_key, s_value in s_resource.items():
                        ext_id = s_value['extra_properties']['id']
                        if resource_id == ext_id:
                            resource_obj = s_resource.get(s_key)
                            resource_name = s_key
                            all_resources = dict(updated_res.items() +
                                                 s_resource.items())
                            self._update_plan_resource(context, data_copy,
                                                       all_resources,
                                                       updated_dep,
                                                       res, resources_list)
                            s_resource[s_key] = all_resources.get(s_key)
                            r_value['properties']['template'] = \
                                json.dumps(template_dict)
                            return
        if not resource_id or not resource_obj:
            msg = "%s resource not found." % resource_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        # Validate properties
        heat_api = heat.API()

        try:
            uncheck_type = ['OS::Neutron::Vip']
            if res_type not in uncheck_type:
                heat_res_type = heat_api.get_resource_type(context, res_type)
                res_properties = heat_res_type.get('properties')
                LOG.debug("Validate the properties to be updated.")
                self._simple_validate_update_properties(properties,
                                                        res_properties)
        except exception.PlanResourcesUpdateError:
            raise
        except Exception as e:
            LOG.error(unicode(e))
            raise exception.PlanResourcesUpdateError(message=unicode(e))

        def _update_simple_fields(resource_id, properties):
            for k, v in properties.items():
                updated_res[resource_id]['properties'][k] = v

        simple_handle_type = ['OS::Neutron::Vip']
        # Update resource
        if 'OS::Nova::Server' == res_type:
            allowed_fields = ['user_data', 'metadata']
            for key, value in properties.items():
                if key in allowed_fields:
                    resource_obj['properties'][key] = value
                else:
                    msg = ("'%s' field of server is not "
                           "allowed to update." % key)
                    LOG.error(msg)
                    raise exception.PlanResourcesUpdateError(message=msg)
        elif res_type in ('OS::Nova::KeyPair'):
            resource_obj['id'] = None
            _update_simple_fields(resource_name, properties)
        elif 'OS::Neutron::SecurityGroup' == res_type:
            brules = []
            for rule in rules:
                if rule.get('protocol') == 'any':
                    rule.pop('protocol', None)
                # Only extract secgroups in first level,
                # ignore the dependent secgroup.
                rg_id = rule.get('remote_group_id')
                if rg_id is not None:
                    rule['remote_mode'] = "remote_group_id"
                    if rg_id == rule.get('security_group_id'):
                        rule.pop('remote_group_id', None)

                rule.pop('tenant_id', None)
                rule.pop('id', None)
                rule.pop('security_group_id', None)
                rule = dict((k, v) for k, v in rule.items() if v is not None)
                brules.append(rule)
            resource_obj['id'] = None
            updated_res[resource_name]['properties']['rules'] = brules
            _update_simple_fields(resource_name, properties)
        elif 'OS::Neutron::FloatingIP' == res_type:
            resource_obj['id'] = None
            _update_simple_fields(resource_name, properties)
        elif 'OS::Neutron::Port' == res_type:
            self._update_port_resource(context, resource_name, updated_res,
                                       res)
        elif 'OS::Neutron::Net' == res_type:
            self._update_network_resource(resource_name, updated_res,
                                          updated_dep, res)
        elif 'OS::Neutron::Subnet' == res_type:
            self._update_subnet_resource(resource_name, updated_res,
                                         updated_dep, res, resources_list)
        elif res_type in simple_handle_type:
            _update_simple_fields(resource_name, properties)
        elif 'OS::Cinder::Volume' == res_type:
            resource_obj['id'] = None
            resource_obj['extra_properties']['copy_data'] = \
                d_copy and data_copy
            _update_simple_fields(resource_name, properties)
        else:
            msg = "%s resource is unsupported to update." % res_type
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

    def _update_network_resource(self, resource_name, updated_res,
                                 updated_dep, net_res):
        LOG.debug("Update network %s resource with %s.",
                  net_res['resource_id'], net_res)

        properties = net_res
        resource_id = properties.pop('resource_id', None)
        properties.pop('resource_type', None)

        # need to modify
        LOG.info("Network <%s> is the same as original network. "
                 "updating the org_net info", resource_id)
        self._update_org_net_info(resource_id, resource_name,
                                  updated_res, updated_dep)

        if properties.get('value_specs') and \
                not properties.get('value_specs').\
                        get('provider:segmentation_id'):
            if updated_res[resource_name]['properties']. \
                    get('value_specs').get('provider:segmentation_id'):
                updated_res[resource_name]['properties']. \
                    get('value_specs').pop('provider:segmentation_id')
        elif not properties.get('value_specs'):
            if updated_res[resource_name]['properties']. \
                    get('value_specs').get('provider:segmentation_id'):
                updated_res[resource_name]['properties']. \
                    get('value_specs').pop('provider:segmentation_id')

        # Update other fields.
        for k, v in properties.items():
            updated_res[resource_name]['properties'][k] = v

    def _update_subnet_resource(self, subnet_name, updated_res,
                                updated_dep, subnet_res, resources_list):
        LOG.debug("Update subnet %s resource with %s.",
                  subnet_res['resource_id'], subnet_res)

        properties = subnet_res
        properties.pop('resource_id', None)
        properties.pop('resource_type', None)

        self._update_org_subnet_info(subnet_name, updated_res, updated_dep,
                                     resources_list)
        # Update other fields.
        for k, v in properties.items():
            updated_res[subnet_name]['properties'][k] = v

    def _remove_org_depends(self, org_dependices,
                            new_updated_dep, updated_res):
        org_dep_also_exist = []
        for dep in org_dependices:
            for key, value in new_updated_dep.items():
                if dep['id'] in [d['id'] for d in value['dependencies']]:
                    org_dep_also_exist.append(dep['id'])
                    break
        delete_deps = [item['id'] for item in org_dependices if
                       item['id'] not in org_dep_also_exist]
        for dep in delete_deps:
            res_key = None
            for i_k, i_r in updated_res.items():
                if i_r['id'] == dep:
                    res_key = i_k
                    updated_res.pop(i_k)
                    break
            dependices = new_updated_dep.get(res_key)['dependencies']
            new_updated_dep.pop(res_key)
            if dependices:
                self._remove_org_depends(dependices, new_updated_dep,
                                         updated_res)

    def _extract_resources(self, context, id, type, updated_res):
        if type == 'OS::Cinder::VolumeType':
            vtr = volumes.VolumeType(context, updated_res)
            # resource_ids = [id]
            # resources = vtr.extract_volume_types(resource_ids)
            return vtr.get_collected_resources()
        elif type == 'OS::Cinder::Qos':
            vor = volumes.QosResource(context, updated_res)
            # resources = vor.extract_qos(id)
            return vor.get_collected_resources()

    def _decide_res_name(self, r_type, names):
        i = 0
        for j in names:
            if j.startswith(r_type):
                i += 1
        return i

    # def _replace_old_res(self, src, des, res_map):
    #

    def _add_new_res_and_dep(self, resource_name, res_obj,
                             updated_res, updated_dep):
        updated_res.pop(resource_name, None)
        updated_dep.pop(resource_name, None)
        new_resources = res_obj.get_collected_resources()
        new_dependencies = res_obj.get_collected_dependencies()
        ori_res = self._actual_id_to_resource_id(new_resources)
        ori_dep = self._actual_id_to_resource_id(new_dependencies)
        updated_res.update(ori_res)
        updated_dep.update(ori_dep)

    def _replace_plan_resource(self, context, updated_res,
                               updated_dep, rep_res, resources_list):
        properties = copy.deepcopy(rep_res)
        resource_id = properties.pop('src_id', None)
        new_res_id = properties.pop('des_id', None)
        res_type = properties.pop('resource_type', None)
        resource_obj = None
        resource_name = None
        des_name = None
        # if the new res exist in extracted resource, then return
        for i_key, i_value in updated_res.items():
            ext_id = i_value['extra_properties']['id']
            if resource_id == ext_id:
                resource_obj = updated_res.get(i_key)
                resource_name = i_key
            elif new_res_id == ext_id:
                des_name = i_key
            else:
                continue
        if not resource_id or not resource_obj:
            for r_key, r_value in updated_res.items():
                    r_type = r_value.get('type')
                    if r_type == 'OS::Heat::Stack':
                        template = r_value['properties'].get('template')
                        template_dict = json.loads(template)
                        s_resource = template_dict.get('resources', {})
                        for s_key, s_value in s_resource.items():
                            ext_id = i_value['extra_properties']['id']
                            if resource_id == ext_id:
                                resource_obj = updated_res.get(i_key)
                                resource_name = i_key
                            elif new_res_id == ext_id:
                                des_name = i_key
                        if resource_id and resource_obj:
                            all_resources = dict(updated_res.items() +
                                                 s_resource.items())
                            self._replace_plan_resource(context, all_resources,
                                                        updated_dep,
                                                        rep_res,
                                                        resources_list)
                            s_resource[s_key] = all_resources.get(s_key)
                            r_value['properties']['template'] = json.dumps(
                                template_dict)
                            return
        if not resource_id or not resource_obj:
            msg = "%s resource not found." % resource_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)
        # replace resource
        if 'OS::Nova::KeyPair' == res_type:
            ir = InstanceResource(context)
            kp_res = None
            if not des_name:
                kp_res = ir.extract_keypairs([new_res_id])[0]
                kp_res.name = "keypair_%s" + self._decide_res_name(
                    'keypair',
                    updated_res.keys())
                new_obj_name = kp_res.name
            else:
                new_obj_name = des_name
            for i_key, i_value in updated_res.items():
                if i_value['type'] == 'OS::Nova::Server':
                    get_name = i_value['properties']['flavor']['get_resource']
                    if get_name == resource_name:
                        i_value['properties']['flavor']['get_resource'] = \
                            new_obj_name
            dependencies = updated_dep.get(resource_name)['dependencies']
            if dependencies:
                self._remove_org_depends(dependencies, updated_dep,
                                         updated_res)
            if not des_name:
                self._add_new_res_and_dep(resource_name, kp_res, updated_res,
                                          updated_dep)
        elif 'OS::Neutron::SecurityGroup' == res_type:
            sec_res = None
            if not des_name:
                nr = SecGroup(context)
                sec_res = nr.extract_secgroups([new_res_id])[0]
                sec_res.name = "security_group_%s" + self._decide_res_name(
                    'security_group',
                    updated_res.keys())
                new_obj_name = sec_res.name
            else:
                new_obj_name = des_name
            for i_key, i_value in updated_res.items():
                if i_value['type'] == 'OS::Neutron::Port':
                    sec_grp = i_value['properties']['security_groups']
                    for i_sec in sec_grp:
                        if i_sec['get_resource'] == resource_name:
                            i_sec['get_resource'] = new_obj_name
            dependencies = updated_dep.get(resource_name)['dependencies']
            if dependencies:
                self._remove_org_depends(dependencies, updated_dep,
                                         updated_res)
            if not des_name:
                self._add_new_res_and_dep(resource_name, sec_res, updated_res,
                                          updated_dep)
        elif 'OS::Neutron::FloatingIP' == res_type:
            pass
        elif 'OS::Neutron::Net' == res_type:
            self._replace_network_resource(context, resource_name, des_name,
                                           updated_res, updated_dep, rep_res)
        elif 'OS::Neutron::Subnet' == res_type:
            self._replace_subnet_resource(context, resource_name, des_name,
                                          updated_res, updated_dep, rep_res)
        # elif res_type in simple_handle_type:
        #     _update_simple_fields(resource_id, properties)
        elif 'OS::Cinder::Volume' == res_type:
            pass
        elif 'OS::Cinder::VolumeType' == res_type:
            vt_res = None
            if not des_name:
                vtr = volumes.VolumeType(context)
                vt_res = vtr.extract_volume_type(new_res_id)
                vt_res.name = "volume_type_%s" + self._decide_res_name(
                    'volume_type',
                    updated_res.keys())
                new_obj_name = vt_res.name
            else:
                new_obj_name = des_name
            for i_key, i_value in updated_res.items():
                if i_value['type'] == 'OS::Cinder::Volume':
                    get_name = \
                        i_value['properties']['volume_type']['get_resource']
                    if get_name == resource_name:
                        i_value['properties']['volume_type']['get_resource'] = \
                            new_obj_name
            dependencies = updated_dep.get(resource_name)['dependencies']
            if dependencies:
                self._remove_org_depends(dependencies, updated_dep,
                                         updated_res)
            if not des_name:
                self._add_new_res_and_dep(resource_name, vt_res, updated_res,
                                          updated_dep)
        else:
            msg = "%s resource is unsupported to update." % res_type
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
                    and (value.keys()[0] in ('get_resource', 'get_param',
                                             'get_attr')):
                return True
            else:
                return False

        for key, value in args.items():
            # Validate whether property exists.
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
                msg = ("The type of property (%s: %s) is incorrect "
                       "(expect %s type)." % (key, value, expected_type))
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
                        self._simple_validate_update_properties(
                            v,
                            child_schema['schema'])
                elif child_type not in (list, dict):
                    for v in value:
                        if not _validate_type(v, child_type):
                            msg = "%s is not string type." % v
                            LOG.error(msg)
                            raise exception. \
                                PlanResourcesUpdateError(message=msg)

    def _update_port_resource(self, context, port_name,
                              updated_res, port_res):
        LOG.debug("Update port %s resource with %s.",
                  port_res['resource_id'], port_res)
        properties = port_res
        resource_obj = updated_res[port_name]
        properties.pop('resource_type', None)
        properties.pop('resource_id', None)
        # Only fixed_ips can be updated.
        ips_to_update = properties.pop('fixed_ips')
        if not ips_to_update:
            msg = "Only 'fixed_ips' property is allowed be updated on a port."
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        # Validate the number of ips on a port
        original_ips = resource_obj['properties'].get('fixed_ips')
        if len(original_ips) != len(ips_to_update):
            msg = "The number of fixed ips must remain the same."
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        for item in ips_to_update:
            ip_address = item.get('ip_address')
            ip_index = ips_to_update.index(item)
            if ip_address:
                original_ips[ip_index]['ip_address'] = ip_address

        # we need to create new port
        resource_obj['id'] = None
        # Update other fields.
        for k, v in properties.items():
            updated_res[port_name]['properties'][k] = v

    def _replace_subnet_resource(self, context, sub_name, des_name,
                                 updated_res, updated_dep, sub_res):

        LOG.debug("replace subnet %s resource with %s.",
                  sub_res['src_id'], sub_res)

        properties = sub_res
        new_res_id = properties.pop('attach_id', None)
        properties.pop('src_type', None)

        if new_res_id and not uuidutils.is_uuid_like(new_res_id):
            msg = "Subnet id <%s> must be uuid." % new_res_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        subnet_res = None
        if not des_name:
            nr = NetworkResource(context)
            subnet_res = nr.extract_subnets([new_res_id])[0]

            # Update subnet info
            subnet_res.name = "subnet_%s" + self._decide_res_name(
                'subnet',
                updated_res.keys())
            new_obj_name = subnet_res.name
        else:
            new_obj_name = des_name

        for i_key, i_value in updated_res.items():
            if i_value['type'] == 'OS::Neutron::Port':
                fix_list = \
                    i_value['properties']['fixed_ips']
                for i_s in fix_list:
                    i_sub = i_s.get('subnet_id', {})
                    if i_sub and i_sub['get_resource'] == sub_name:
                        i_sub['get_resource'] = new_obj_name

        dependencies = updated_dep.get(sub_name)['dependencies']
        if dependencies:
            self._remove_org_depends(dependencies, updated_dep,
                                     updated_res)
        if not des_name:
            self._add_new_res_and_dep(sub_name, subnet_res, updated_res,
                                      updated_dep)

    def _update_org_net_info(self, resource_id, net_name,
                             updated_res, updated_dep):
        # set the related resourece id dependencied on net resource_id
        net_update_resource = ["OS::Neutron::Subnet", "OS::Neutron::Port",
                               "OS::Neutron::FloatingIP",
                               "OS::Neutron::Router"]
        sub_update_resource = ["OS::Neutron::RouterInterface",
                               "OS::Neutron::Port"]
        for rid, dep in updated_dep.items():
            if dep['type'] in net_update_resource \
                    and resource_id in [d['id'] for d in dep['dependencies']]:
                net_related_res = updated_res.get(rid)
                net_related_res['id'] = None
                r_id = dep['id']
                for res_id, dep_object in updated_dep.items():
                    if dep_object['type'] in sub_update_resource \
                            and r_id in [d['id'] for
                                         d in dep_object['dependencies']]:
                        sub_related_res = updated_res.get(res_id)
                        sub_related_res['id'] = None
        # set the net resourece id
        net_res = updated_res.get(net_name)
        net_res['id'] = None

    def _update_org_subnet_info(self, subnet_name, updated_res,
                                updated_dep, resources_list):
        res_dependencies_key = updated_dep.get(subnet_name)['dependencies']
        for key in [d['id'] for d in res_dependencies_key]:
            res_obj = [i_r for (i_k, i_r) in updated_res.items()
                       if key == i_r['extra_properties']['id']][0]
            res_name = res_obj['name']
            if res_obj['type'] == "OS::Neutron::Net":
                self._update_org_net_info(key, res_name,
                                          updated_res, updated_dep)
                need_pop_seg = True
                for res in resources_list:
                    if key == res.get('resource_id'):
                        need_pop_seg = False
                        break
                if need_pop_seg:
                    if updated_res[res_name]['properties'].\
                            get('value_specs').get('provider:segmentation_id'):
                        updated_res[res_name]['properties'].\
                            get('value_specs').pop('provider:segmentation_id')

    def _replace_network_resource(self, context, resource_name, des_name,
                                  updated_res, updated_dep, n_res):

        LOG.debug("replace network %s resource with %s.",
                  n_res['src_id'], n_res)

        properties = n_res
        resource_id = properties.pop('src_id', None)
        new_res_id = properties.pop('des_id', None)

        net = self.neutron_api.get_network(context, new_res_id)
        subnets = net.get('subnets', [])
        if not subnets:
            msg = "No subnets found in network %s." % new_res_id
            LOG.error(msg)
            raise exception.PlanResourcesUpdateError(message=msg)

        # Validate whether network exists on a server.
        self._validate_server_network_duplication(resource_name,
                                                  resource_id, updated_res)

        # Extracted network resource.
        net_res = None
        if not des_name:
            nr = NetworkResource(context)
            net_res = nr.extract_nets([new_res_id])[0]

            # Update network resource.
            net_res.name = "network_%s" + self._decide_res_name(
                'network',
                updated_res.keys())
            new_name = net_res.name
        else:
            new_name = des_name

        for i_key, i_value in updated_res.items():
            if i_value['type'] == 'OS::Neutron::Subnet':
                get_name = \
                    i_value['properties']['network_id']['get_resource']
                if get_name == resource_name:
                    i_value['properties']['network_id']['get_resource'] = \
                        new_name
            elif i_value['type'] == 'OS::Neutron::Port':
                net_id = i_value['properties']['network_id']
                if net_id['get_resource'] == resource_name:
                    net_id['get_resource'] = new_name
        dependencies = updated_dep.get(resource_name)['dependencies']
        if dependencies:
            self._remove_org_depends(dependencies, updated_dep,
                                     updated_res)
        if not des_name:
            self._add_new_res_and_dep(resource_name, net_res, updated_res,
                                      updated_dep)

    def _validate_server_network_duplication(self, net_res_id_to_update,
                                             net_id, updated_res):
        LOG.debug("Validate whether network exists on a server.")

        for res in updated_res.values():

            if res['type'] != "OS::Nova::Server":
                continue

            networks = res['properties'].get('networks')
            if not networks:
                continue

            exist_nets = []
            need_validate = False

            def _get_param(res, param_id):
                if isinstance(param_id, six.string_types):
                    return res['parameters'].get(param_id, {}).get('default')

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
                            exist_nets.append(updated_res[net_res_id]['id'])

            for net in networks:
                port_res_id = net.get('port', {}).get('get_resource')
                net_uuid = net.get('uuid', {})
                network = net.get('network', {})

                if port_res_id:
                    port_res = updated_res.get(port_res_id)

                    if not port_res:
                        continue

                    network_id = port_res['properties'].get('network_id')

                    if uuidutils.is_uuid_like(network_id):
                        exist_nets.append(network_id)
                    elif isinstance(network_id, dict) and len(network_id) == 1:
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
                                    exist_nets.append(net_res['id'])

                if net_uuid:
                    if _get_net_id(net_uuid) is True:
                        need_validate = True

                if network:
                    if _get_net_id(network) is True:
                        need_validate = True

            if need_validate and net_id in exist_nets:
                msg = ("Duplicate networks <%s> found on server <%s>."
                       % (net_id, res.name))
                LOG.error(msg)
                raise exception.PlanResourcesUpdateError(message=msg)

    def build_dependencies(self, resources):
        def get_dependencies(properties, deps):
            if isinstance(properties, dict) and len(properties) == 1:
                key = properties.keys()[0]
                value = properties[key]
                if key == "get_resource":
                    if isinstance(value, six.string_types) \
                            and value in resources.keys():
                        i_res = resources.get(value)
                        app = {
                            'type': i_res['type'],
                            'id': i_res['id'],
                            'name': i_res['name']
                        }
                        deps.append(app)
                elif key == "get_attr":
                    if isinstance(value, list) and len(value) >= 1 \
                            and isinstance(value[0], six.string_types) \
                            and value[0] in resources.keys():
                        i_res = resources.get(value[0])
                        app = {
                            'type': i_res['type'],
                            'id': i_res['id'],
                            'name': i_res['name']
                        }
                        deps.append(app)

                else:
                    get_dependencies(properties[key], deps)
            elif isinstance(properties, dict):
                for p in properties.values():
                    get_dependencies(p, deps)
            elif isinstance(properties, list):
                for p in properties:
                    get_dependencies(p, deps)

        if not resources:
            return

        dependencies = {}
        for res in resources.values():
            deps = []
            get_dependencies(res['properties'], deps)
            # remove duplicate dependencies
            deps = {}.fromkeys(deps).keys()
            new_dependencies = resource.ResourceDependency(
                res['id'], res['name'],
                res['properties'].get('name', ''), res['type'],
                dependencies=deps)
            dependencies[res['name']] = new_dependencies
        return dependencies
