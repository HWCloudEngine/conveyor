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

from oslo_log import log as logging

from conveyor import exception
from conveyor import network
from conveyor.resource.driver import base
from conveyor.resource.driver import networks
from conveyor.resource import resource

LOG = logging.getLogger(__name__)


class FloatIps(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        super(FloatIps, self).__init__(context)
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_floatingips(self, floatingip_ids):

        # 1. get floating ips info
        floatingip_objs = []
        floatingipResources = []

        if not floatingip_ids:
            LOG.debug('Extract resources of floating ips.')
            return floatingipResources

        else:
            LOG.debug('Extract resources of floating ips: %s', floatingip_ids)
            # remove duplicate floatingips
            floatingip_ids = {}.fromkeys(floatingip_ids).keys()
            for floatingip_id in floatingip_ids:
                try:
                    floatingip = self.neutron_api.get_floatingip(self.context,
                                                                 floatingip_id)
                    floatingip_objs.append(floatingip)
                except Exception as e:
                    msg = "FloatingIp resource <%s> could not be found. %s" \
                            % (floatingip_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for floatingip in floatingip_objs:
            floatingip_id = floatingip.get('id')
            floatingip_res = self._collected_resources.get(floatingip_id)
            if floatingip_res:
                floatingipResources.append(floatingip_res)
                continue

            properties = {}
            dependencies = []

            floating_network_id = floatingip.get('floating_network_id')
            floating_ip_address = floatingip.get('floating_ip_address')

            if not floating_network_id or not floating_ip_address:
                msg = "FloatingIp information is abnormal. \
                      'floating_network_id' or 'floating_ip_address' is None"
                LOG.error(msg)
                raise exception.ResourceAttributesException(message=msg)

            # 2.get network and subnetwork for floating ip
            col_res = self._collected_resources
            cold_eps = self._collected_dependencies
            network_cls = \
                networks.NetworkResource(self.context,
                                         collected_resources=col_res,
                                         collected_dependencies=cold_eps)

            net_res =  \
                network_cls.extract_nets([floating_network_id],
                                         with_subnets=True)

            # refresh collected resource in order
            # to add network and subnet resource
            self._collected_resources = \
                network_cls.get_collected_resources()
            self._collected_dependencies = \
                network_cls.get_collected_dependencies()

            properties['floating_network_id'] = \
                {'get_resource': net_res[0].name}

            resource_type = "OS::Neutron::FloatingIP"
            resource_name = 'floatingip_%d' % \
                self._get_resource_num(resource_type)
            floatingip_res = resource.Resource(resource_name, resource_type,
                                               floatingip_id,
                                               properties=properties)

            # remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            floatingip_dep = \
                resource.ResourceDependency(floatingip_id, resource_name,
                                            '',
                                            resource_type)
            dep_res_name = net_res[0].properties.get('name', '')
            floatingip_dep.add_dependency(net_res[0].id, dep_res_name,
                                          net_res[0].name, net_res[0].type)

            self._collected_resources[floatingip_id] = floatingip_res
            self._collected_dependencies[floatingip_id] = floatingip_dep
            floatingipResources.append(floatingip_res)

        if floatingip_ids and not floatingipResources:
            msg = "FloatingIp resource extracted failed, \
                    can't find the floatingip with id of %s." % floatingip_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        return floatingipResources
