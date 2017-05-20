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
from conveyor.resource import resource

LOG = logging.getLogger(__name__)


class SecGroup(base.resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_secgroups(self, secgroup_ids):

        secgroup_objs = []
        secgroupResources = []

        if not secgroup_ids:
            LOG.debug('Extract resources of security groups')
            secgroup_list = self.neutron_api.secgroup_list(self.context)
            secgroup_objs = filter(self._tenant_filter, secgroup_list)
        else:
            LOG.debug('Extract resources of security groups: %s',
                      secgroup_ids)
            # remove duplicate secgroups
            secgroup_ids = {}.fromkeys(secgroup_ids).keys()
            for sec_id in secgroup_ids:
                try:
                    sec = self.neutron_api.get_security_group(self.context,
                                                              sec_id)
                    secgroup_objs.append(sec)
                except Exception as e:
                    msg = "SecurityGroup resource <%s> could " \
                          "not be found. %s" % (sec_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for sec in secgroup_objs:
            sec_id = sec.get('id')
            sec_res = self._collected_resources.get(sec_id)
            if sec_res:
                secgroupResources.append(sec_res)
                continue

            if sec.get('name') == 'default':
                sec['name'] = '_default'

            properties = {
                'description': sec.get('description'),
                'name': sec.get('name'),
            }

            resource_type = "OS::Neutron::SecurityGroup"
            resource_name = 'security_group_%d' % \
                self._get_resource_num(resource_type)
            sec_res = resource.Resource(resource_name, resource_type,
                                        sec_id, properties=properties)

            # Put secgroup into collected_resources first before
            # extracting rules to avoid recycle dependencies.
            self._collected_resources[sec_id] = sec_res

            # Extract secgroup rules.
            rules, dependencies = \
                self._build_rules(sec.get('security_group_rules'))
            self._collected_resources[sec_id].add_property('rules', rules)

            # remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            sec_dep = resource.ResourceDependency(sec_id, sec.get('name'),
                                                  resource_name,
                                                  resource_type,
                                                  dependencies=dependencies)

            self._collected_dependencies[sec_id] = sec_dep
            secgroupResources.append(sec_res)

        if secgroup_ids and not secgroupResources:
            msg = "Security group resource extracted failed, \
                   can't find the Security group with id of %s." % \
                   secgroup_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        return secgroupResources

    def _build_rules(self, rules):
        brules = []
        dependencies = []
        for rule in rules:
            if rule.get('protocol') == 'any':
                del rule['protocol']
            # Only extract secgroups in first level,
            # ignore the dependent secgroup.
            rg_id = rule.get('remote_group_id')
            if rg_id is not None:
                rule['remote_mode'] = "remote_group_id"
                if rg_id == rule.get('security_group_id'):
                    del rule['remote_group_id']

            del rule['tenant_id']
            del rule['id']
            del rule['security_group_id']
            rule = dict((k, v) for k, v in rule.items() if v is not None)
            brules.append(rule)
        return brules, dependencies
