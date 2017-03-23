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

from conveyor import compute
from conveyor import exception
from conveyor import network

from oslo_log import log as logging
from conveyor.resource import resource
from conveyor.resource.driver import base
from conveyor.resource.driver import networks
from conveyor.resource.driver import instances

LOG = logging.getLogger(__name__)


class LoadbalanceVip(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_loadbalanceVips(self, vip_ids):
        if not vip_ids:
            _msg = 'Create LB vip resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)

        try:
            for vip_id in vip_ids:
                self.extract_loadbalanceVip(vip_id)
        except exception.ResourceExtractFailed:
            raise
        except Exception as e:
            _msg = 'Create LB vip resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)

    def extract_loadbalanceVip(self, vip_id, pool_name):

        # if vip resource exist in collect resource
        vip_col = self._collected_resources.get(vip_id)
        if vip_col:
            return vip_col
        dependences = []
        properties = {}

        # 1. query vip info
        try:
            vip_info = self.neutron_api.get_vip(self.context, vip_id)
        except Exception as e:
            _msg = 'Create LB vip resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        properties['protocol_port'] = vip_info.get('protocol_port')
        properties['session_persistence'] = vip_info.get('session_persistence')
        # properties['protocol'] = vip_info.get('protocol')
        vip_name = vip_info.get('name')
        vip_address = vip_info.get('address')
        vip_admin = vip_info.get('admin_state_up')
        vip_connection = vip_info.get('connection_limit')
        vip_des = vip_info.get('description')
        if vip_name:
            properties['name'] = vip_name

        if vip_address:
            properties['address'] = vip_address

        if vip_admin:
            properties['admin_state_up'] = vip_admin
        if vip_connection:
            properties['connection_limit'] = vip_connection
        if vip_des:
            properties['description'] = vip_des

        properties['pool_id'] = {'get_resource': pool_name}
        dependences.append(pool_name)

        # build subnet resource and build dependence relation
        subnet_id = vip_info.get('subnet_id')

        if subnet_id:
            newtwork_driver = \
                networks.NetworkResource(self.context,
                                         collected_resources= \
                                         self._collected_resources,
                                         collected_parameters= \
                                         self._collected_parameters,
                                         collected_dependencies= \
                                         self._collected_dependencies)
            subnet_ids = []
            subnet_ids.append(subnet_id)
            subnet_res = newtwork_driver.extract_subnets(subnet_ids)
            dependences.append(subnet_res[0].name)
            properties['subnet'] = {'get_resource': subnet_res[0].name}

            # update collect resources and dependences
            self._collected_resources = \
                newtwork_driver.get_collected_resources()

            self._collected_dependencies = \
                newtwork_driver.get_collected_dependencies()

        vip_type = "OS::Neutron::Vip"
        vip_name = 'loadbalanceVip_%d' % self._get_resource_num(vip_type)

        # build listener resource and build dependence relation
        listener_extras = vip_info.get('extra_listeners')
        listener_ids = None
        if listener_extras:
            listener_ids = []
            for listener_extra in listener_extras:
                listener_id = listener_extra.get('id')
                listener_ids.append(listener_id)

        if listener_ids:
            listener_driver = \
                LoadbalanceListener(self.context,
                                    collected_resources= \
                                    self._collected_resources,
                                    collected_parameters= \
                                    self._collected_parameters,
                                    collected_dependencies= \
                                    self._collected_dependencies)
            listener_driver.extract_loadbalanceListeners(listener_ids,
                                                         vip_id,
                                                         vip_name)

            # update collect resources and dependences
            self._collected_resources = \
                listener_driver.get_collected_resources()

            self._collected_dependencies = \
                listener_driver.get_collected_dependencies()

        vip_res = resource.Resource(vip_name, vip_type,
                                    vip_id, properties=properties)

        # remove duplicate dependencies
        dependencies = {}.fromkeys(dependences).keys()
        vip_dep = resource.ResourceDependency(vip_id, '',
                                              vip_name, vip_type,
                                              dependencies=dependencies)

        self._collected_resources[vip_id] = vip_res
        self._collected_dependencies[vip_id] = vip_dep

        return vip_res


class LoadbalancePool(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_loadbalancePools(self, pool_ids):

        if not pool_ids:
            _msg = 'Create LB pool resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)

        try:
            for pool_id in pool_ids:
                self.extract_loadbalancePool(pool_id)
        except exception.ResourceExtractFailed:
            raise
        except Exception as e:
            _msg = 'Create LB pool resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)

    def extract_loadbalancePool(self, pool_id):

        pool_col = self._collected_resources.get(pool_id)

        if pool_col:
            return pool_col

        dependencies = []
        properties = {}

        # 1. query pool info
        try:
            pool = self.neutron_api.show_pool(self.context, pool_id)
        except Exception as e:
            LOG.error('Create LB pool %(pool)s resource error %(error)s',
                      {'pool': pool_id, 'error': e})
            _msg = 'Create LB pool resource error: %s' % e
            raise exception.ResourceExtractFailed(_msg)

        pool_info = pool.get('pool')

        properties['lb_method'] = pool_info.get('lb_method')
        properties['protocol'] = pool_info.get('protocol')
        pool_name = pool_info.get('name')
        pool_des = pool_info.get('description')
        pool_admin = pool_info.get('admin_state_up')
        if pool_name:
            properties['name'] = pool_name
        if pool_des:
            properties['description'] = pool_des
        if pool_admin:
            properties['admin_state_up'] = pool_admin

        # properties['provider'] = pool_info.get('provider')
        pool_type = "OS::Neutron::Pool"
        pool_name = 'loadbalancePool_%d' % self._get_resource_num(pool_type)

        # 2. build vip of pool and build dependence relation
        vip_id = pool_info.get('vip_id')
        if vip_id:
            vip_driver = \
                LoadbalanceVip(self.context,
                               collected_resources= \
                               self._collected_resources,
                               collected_parameters= \
                               self._collected_parameters,
                               collected_dependencies= \
                               self._collected_dependencies)
            vip_res = vip_driver.extract_loadbalanceVip(vip_id, pool_name)
            properties['vip'] = {'get_resource': vip_res.name}
            # vip resource in lb resource list
            self._collected_resources = vip_driver.get_collected_resources()
            self._collected_dependencies = \
                vip_driver.get_collected_dependencies()

        subnet_id = pool_info.get('subnet_id')

        if subnet_id:
            # 3. build subnet resource and build dependence relation
            newtwork_driver = \
                networks.NetworkResource(self.context,
                                         collected_resources= \
                                         self._collected_resources,
                                         collected_parameters= \
                                         self._collected_parameters,
                                         collected_dependencies= \
                                         self._collected_dependencies)
            subnet_ids = []
            subnet_ids.append(subnet_id)
            subnet_res = newtwork_driver.extract_subnets(subnet_ids)
            dependencies.append(subnet_res[0].name)
            properties['subnet'] = {'get_resource': subnet_res[0].name}

            # 3.2 add subnet resource in lb resource list
            self._collected_resources = \
                newtwork_driver.get_collected_resources()
            self._collected_dependencies = \
                newtwork_driver.get_collected_dependencies()

        # 4. build members of pool and build dependence relation
        member_ids = pool_info.get('members')

        if member_ids:
            lb_member_driver = \
                LoadbalanceMember(self.context,
                                  collected_resources= \
                                  self._collected_resources,
                                  collected_parameters= \
                                  self._collected_parameters,
                                  collected_dependencies= \
                                  self._collected_dependencies)
            lb_member_driver.extract_loadbalanceMembers(member_ids, pool_name)

            # update collect resource
            self._collected_resources = \
                lb_member_driver.get_collected_resources()
            self._collected_dependencies = \
                lb_member_driver.get_collected_dependencies()

        # 4. query health monitor of pool and build dependence relation
        healthmonitor_ids = pool_info.get('health_monitors')

        if healthmonitor_ids:
            lb_healthmonitor_driver = \
                LoadbalanceHealthmonitor(self.context,
                                         collected_resources= \
                                         self._collected_resources,
                                         collected_parameters= \
                                         self._collected_parameters,
                                         collected_dependencies= \
                                         self._collected_dependencies)
            ids = healthmonitor_ids
            h = lb_healthmonitor_driver.extract_loadbalanceHealthmonitors(ids)

            # update collect resource
            self._collected_resources = \
                lb_healthmonitor_driver.get_collected_resources()
            self._collected_dependencies = \
                lb_healthmonitor_driver.get_collected_dependencies()

            # add all healthmonitor to pool dependences
            monitors = []
            for res in h:
                dependencies.append(res.name)
                monitors.append({'get_resource': res.name})

            properties['monitors'] = monitors

        pool_type = "OS::Neutron::Pool"
        pool_name = 'loadbalancePool_%d' % self._get_resource_num(pool_type)

        pool_res = resource.Resource(pool_name, pool_type,
                                     pool_id, properties=properties)

        # remove duplicate dependencies
        dependencies = {}.fromkeys(dependencies).keys()
        pool_dep = resource.ResourceDependency(pool_id, '',
                                               pool_name, pool_type,
                                               dependencies=dependencies)

        self._collected_resources[pool_id] = pool_res
        self._collected_dependencies[pool_id] = pool_dep


class LoadbalanceListener(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_loadbalanceListeners(self, listener_ids, vip_id, vip_name):
        if not listener_ids:
            _msg = 'Create LB listener resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)

        try:
            for listener_id in listener_ids:
                self.extract_loadbalanceListener(listener_id, vip_id, vip_name)
        except exception.ResourceExtractFailed:
            raise
        except Exception as e:
            _msg = 'Create LB listener resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)

    def extract_loadbalanceListener(self, listener_id, vip_id, vip_name):

        listener_col = self._collected_resources.get(listener_id)

        if listener_col:
            return listener_col

        # 1 query listener info
        try:
            listener = self.neutron_api.show_listener(self.context,
                                                      listener_id,
                                                      vip_id)
        except Exception as e:
            _msg = 'Create LB listener resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        # 2 build listener resource and dependence
        listener_info = listener.get('listener')

        properties = {}
        dependencies = []
        properties['protocol'] = listener_info.get('protocol')
        properties['protocol_port'] = listener_info.get('protocol_port')
        properties['vip_id'] = {'get_resource': vip_name}
        dependencies.append(vip_name)

        listener_type = "OS::Neutron::Listener"
        listener_name = 'loadbalanceListener_%d' % \
            self._get_resource_num(listener_type)

        listener_res = resource.Resource(listener_name, listener_type,
                                         listener_id,
                                         properties=properties)

        # remove duplicate dependencies
        dependencies = {}.fromkeys(dependencies).keys()
        listener_dep = resource.ResourceDependency(listener_id, '',
                                                   listener_name,
                                                   listener_type,
                                                   dependencies=dependencies)

        self._collected_resources[listener_id] = listener_res
        self._collected_dependencies[listener_id] = listener_dep

        return listener_res


class LoadbalanceMember(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self.nova_api = compute.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_loadbalanceMember(self, member_id, pool_name):
        # check resource exist or not
        member_col = self._collected_resources.get(member_id)

        if member_col:
            return member_col

        properties = {}
        dependencies = []

        # query member info

        try:
            member = self.neutron_api.show_member(self.context, member_id)
        except Exception as e:
            _msg = 'Create LB member resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        member_info = member.get('member')
        properties['address'] = member_info.get('address')
        properties['protocol_port'] = member_info.get('protocol_port')
        member_admin = member_info.get('admin_state_up')
        member_weight = member_info.get('weight')
        if member_admin:
            properties['admin_state_up'] = member_admin
        if member_weight:
            properties['weight'] = member_weight
        properties['pool_id'] = {'get_resource': pool_name}
        dependencies.append(pool_name)

        # if member relates to instances
        try:
            server_id = self._get_member_related_vm(properties['address'])

            if server_id:
                instance_driver = instances.InstanceResource(self.context,
                                                             collected_resources= \
                                                             self._collected_resources,
                                                             collected_parameters= \
                                                             self._collected_parameters,
                                                             collected_dependencies= \
                                                             self._collected_dependencies)
                instance_ids = []
                instance_ids.append(server_id)
                reses = instance_driver.extract_instances(instance_ids)
                if reses:
                    instance_res_name = reses[0].name
                    dependencies.append(instance_res_name)

        except Exception as e:
            _msg = 'Create LB member resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        # build member resource and build dependence relation
        member_type = "OS::Neutron::PoolMember"
        member_name = 'loadbalancePoolMember_%d' % \
            self._get_resource_num(member_type)

        member_res = resource.Resource(member_name, member_type,
                                       member_id, properties=properties)

        # remove duplicate dependencies
        dependencies = {}.fromkeys(dependencies).keys()
        member_dep = resource.ResourceDependency(member_id, '',
                                                 member_name, member_type,
                                                 dependencies=dependencies)

        self._collected_resources[member_id] = member_res
        self._collected_dependencies[member_id] = member_dep

        return member_res

    def extract_loadbalanceMembers(self, member_ids, pool_name):

        if not member_ids or not pool_name:
            LOG.error('Create LB member resource error: %s', pool_name)
            _msg = 'Create LB member resource error: member or pool is null.'
            raise exception.InvalidInput(reason=_msg)
        try:
            for member_id in member_ids:
                self.extract_loadbalanceMember(member_id, pool_name)
        except Exception as e:
            _msg = 'Create LB member resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

    def _get_member_related_vm(self, mem_address):

        # 1. query all vm
        servers = self.nova_api.get_all_servers(self.context)

        # 2. find the same address with mem_address of vm
        for server in servers:
            addresses = server.get('addresses', '')
            if not addresses:
                continue
            for k, addrs in addresses.items():
                if not addrs:
                    continue
                for addr in addrs:
                    ip_address = addr.get('addr', None)
                    if mem_address == ip_address:
                        return server.get('id')
        return None


class LoadbalanceHealthmonitor(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_loadbalanceHealthmonitors(self, healthmonitor_ids):

        if not healthmonitor_ids:
            _msg = 'Create LB health monitor resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)

        res_list = []
        try:
            for healthmonitor_id in healthmonitor_ids:
                res = self.extract_loadbalanceHealthmonitor(healthmonitor_id)
                res_list.append(res)
        except exception.ResourceExtractFailed:
            raise
        except Exception as e:
            _msg = 'Create LB health monitor resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        return res_list

    def extract_loadbalanceHealthmonitor(self, healthmonitor_id):

        # check health monitor resource exist or not
        healthmonitor_col = self._collected_resources.get(healthmonitor_id)
        if healthmonitor_col:
            return healthmonitor_col

        try:
            healthmonitor = \
                self.neutron_api.show_health_monitor(self.context,
                                                     healthmonitor_id)
        except Exception as e:
            _msg = 'Create LB health monitor resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        properties = {}

        healthmonitor_info = healthmonitor.get('health_monitor')

        properties['delay'] = healthmonitor_info.get('delay')
        properties['type'] = healthmonitor_info.get('type')
        properties['max_retries'] = healthmonitor_info.get('max_retries')
        properties['timeout'] = healthmonitor_info.get('timeout')

        healthmonitor_code = healthmonitor_info.get('expected_codes')
        healthmonitor_http = healthmonitor_info.get('http_method')
        healthmonitor_admin = healthmonitor_info.get('admin_state_up')
        healthmonitor_url = healthmonitor_info.get('url_path')
        if healthmonitor_code:
            properties['expected_codes'] = healthmonitor_code

        if healthmonitor_http:
            properties['http_method'] = healthmonitor_http

        if healthmonitor_admin:
            properties['admin_state_up'] = healthmonitor_admin

        if healthmonitor_url:
            properties['url_path'] = healthmonitor_url

        healthmonitor_type = "OS::Neutron::HealthMonitor"
        healthmonitor_name = 'loadbalanceHealthmonitor_%d' \
                             % self._get_resource_num(healthmonitor_type)

        healthmonitor_res = resource.Resource(healthmonitor_name,
                                              healthmonitor_type,
                                              healthmonitor_id,
                                              properties=properties)

        healthmonitor_dep = resource.ResourceDependency(healthmonitor_id, '',
                                                        healthmonitor_name,
                                                        healthmonitor_type)

        self._collected_resources[healthmonitor_id] = healthmonitor_res
        self._collected_dependencies[healthmonitor_id] = healthmonitor_dep

        return healthmonitor_res
