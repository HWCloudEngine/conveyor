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

from conveyor import exception
from conveyor import  volume

from oslo_log import log as logging
from conveyor.resource import resource
from conveyor.resource.driver import base
from conveyor.resource.driver.volumes import VolumeResource

LOG = logging.getLogger(__name__)

class ConsistencyGroup(base.resource):

    def __init__(self, context, collected_resources=None,
                collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_consistency_groups(self, cg_ids):
        if not cg_ids:
            _msg='Create consistency groups resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)

        try:
            for cg_id in cg_ids:
                self.extract_consistency_group(cg_id)
        except exception.ResourceExtractFailed:
            raise
        except Exception as e:
            _msg ='Create consistency groups resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)
        
    def extract_consistency_group(self, cg_id):
        # check consistency group resource exist or not
        cgroup_col = self._collected_resources.get(cg_id)
        if cgroup_col:
            return cgroup_col
        try:
            consisgroup = self.cinder_api.get_consisgroup(self.context, cg_id)
        except Exception as e:
            _msg='Create consistency groups resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)
        properties = {}
        cg_info = consisgroup.get('consistencygroup')
        properties['availability_zone'] = cg_info.get('availability_zone')
        properties['name'] = cg_info.get('name')
        properties['description'] = cg_info.get('description')
        cg_type = "OS::Cinder::ConsistencyGroup"
        cg_name = 'consistencyGroup%d' \
                             % self._get_resource_num(cg_type)

        cg_res = resource.Resource(cg_name, cg_type,
                                   cg_id,
                                   properties=properties)
        cg_dependencies = resource.ResourceDependency(cg_id, cg_info.get('name'), 
                                                      cg_name, cg_type)
        volume_types_id = cg_info.get('volume_types')
        volume_driver = VolumeResource(self.context,
                              collected_resources= \
                              self._collected_resources,
                              collected_parameters= \
                              self._collected_parameters,
                              collected_dependencies= \
                              self._collected_dependencies)
        if volume_types_id:
            volume_type_res = volume_driver.extract_volume_types\
                                         (volume_types_id, cg_id)
            volume_type_property = []
            for v in volume_type_res:
                # addd properties
                volume_type_property.append({'get_resource': v.name})
                cg_dependencies.add_dependency(v.name)
        cg_res.add_property('volume_types', volume_type_property)   
        volume_ids = []
        try:
            volumes = self.cinder_api.get_all(self.context)
            for volume in volumes:
                consistencygroup_id = volume.get('consistencygroup_id')
                if consistencygroup_id and consistencygroup_id == cg_id:
                    volume_ids.append(volume.get('id')) 
        except Exception as e:
            _msg='Create consistency groups resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        if volume_ids:
            volume_res = volume_driver.extract_volumes\
                                         (volume_ids, cg_id)

        self._collected_resources = volume_driver.get_collected_resources()
        self._collected_dependencies = volume_driver.get_collected_dependencies()

        self._collected_resources[cg_id] = cg_res
        self._collected_dependencies[cg_id] = cg_dependencies

       
    