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
from oslo_log import log as logging
import oslo_messaging as messaging

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
from conveyor.resource.driver.volumes import Volume
from conveyor.resource import resource
from conveyor import volume

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


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

    def build_reources_topo(self, context, resources):
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
            else:
                LOG.error("The resource type %s is unsupported.", res_type)
                raise exception.ResourceTypeNotSupported(resource_type=
                                                         res_type)

        res_num = len(instance_ids) + len(volume_ids) + len(network_ids) + \
                  len(router_ids) + len(secgroup_ids) + \
                  len(loadbalancer_ids) + len(stack_ids) + \
                  len(floatingip_ids) + len(pool_ids)
        if 0 == res_num:
            msg = "No valid resources found, please check " \
                  "the resource id and type."
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
                                             collected_resources=
                                             new_resources,
                                             collected_dependencies=
                                             new_dependencies)
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

        ori_res = self._actual_id_to_resource_id(new_resources)
        ori_dep = self._actual_id_to_resource_id(new_dependencies)
        return ori_res, ori_dep

    def _actual_id_to_resource_id(self, res_or_dep):
        new_res = {}
        if isinstance(res_or_dep, dict):
            for v in res_or_dep.values():
                if isinstance(v, resource.Resource):
                    new_res[v.name] = v.to_dict()
                elif isinstance(v, resource.ResourceDependency):
                    new_res[v.name_in_template] = v.to_dict()

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
