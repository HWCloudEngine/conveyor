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
from conveyor.resource.driver import base
from conveyor.resource import resource
from conveyor.resource import resource_state
from conveyor import volume

LOG = logging.getLogger(__name__)


class VolumeResource(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_volumes(self, volume_ids):

        volume_dicts = []
        volumeResources = []

        if not volume_ids:
            LOG.info('Extract resources of all volumes.')
            volume_dicts = self.cinder_api.get_all(self.context)
        else:
            LOG.info('Extract resources of volumes: %s', volume_ids)
            # remove duplicate volume
            volume_ids = {}.fromkeys(volume_ids).keys()
            for volume_id in volume_ids:
                try:
                    volume = self.cinder_api.get(self.context, volume_id)
                    volume_dicts.append(volume)
                except Exception as e:
                    msg = "Volume resource <%s> could not be found. %s" \
                            % (volume_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for volume in volume_dicts:
            volume_id = volume['id']
            vol_state = volume.get('status', None)
            if vol_state not in resource_state.VOLUME_CLONE_STATE:
                LOG.error("Volume %(id)s state is %(state)s not available \
                           or in-use", {'id': volume_id, 'state': vol_state})
                raise exception.PlanCreateFailed
            volume_res = self._collected_resources.get(volume_id)
            if volume_res:
                volumeResources.append(volume_res)
                continue

            properties = {
                'size': volume['size'],
                'name': volume['display_name'],
                'availability_zone': volume['availability_zone']
            }

            if volume.get('display_description'):
                properties['description'] = volume['display_description']

            vol_metadata = volume.get('volume_metadata', None)
            if vol_metadata:
                vol_metadata.pop('__hc_vol_id', None)
                vol_metadata.pop('__openstack_region_name', None)
                properties['metadata'] = vol_metadata

            resource_type = "OS::Cinder::Volume"
            resource_name = 'volume_%d' % self.\
                _get_resource_num(resource_type)
            volume_res = resource.Resource(resource_name, resource_type,
                                           volume_id, properties=properties)
            volume_dep = resource.ResourceDependency(volume_id,
                                                     resource_name,
                                                     volume['display_name'],
                                                     resource_type)

            volume_res.add_extra_property('status', vol_state)
            volume_res.add_extra_property('copy_data', True)
            volume_type_name = volume['volume_type']
            if volume_type_name:
                volume_types = self.cinder_api.volume_type_list(self.context)
                volume_type_id = None

                for vtype in volume_types:
                    if vtype['name'] == volume_type_name:
                        volume_type_id = vtype['id']
                        break
                if volume_type_id:
                    volume_type_res = \
                        self.extract_volume_types([volume_type_id])
                    if volume_type_res:
                        t_name = volume_type_res[0].name
                        volume_res.add_property('volume_type',
                                                {'get_resource': t_name})
                        dep_res_name = \
                            volume_type_res[0].properties.get('name', '')
                        volume_dep.add_dependency(volume_type_res[0].id,
                                                  volume_type_res[0].name,
                                                  dep_res_name,
                                                  volume_type_res[0].type)

            if volume['bootable'] and volume.get('volume_image_metadata'):
                image_id = volume['volume_image_metadata'].get('image_id')
                if image_id:
                    image_para_name = self.extract_image(image_id)
                    description = ("Image to use to boot server or volume")
                    constraints = [{'custom_constraint': "glance.image"}]
                    volume_res.add_parameter(image_para_name, description,
                                             default=image_id,
                                             constraints=constraints)
                    volume_res.add_property('image',
                                            {'get_param': image_para_name})
                    volume_res.add_extra_property('boot_index', 0)

            self._collected_resources[volume_id] = volume_res
            self._collected_dependencies[volume_id] = volume_dep

            volumeResources.append(volume_res)

        if volume_ids and not volumeResources:
            msg = "Volume resource extracted failed, \
                    can't find the volume with id of %s." % volume_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        LOG.info('Extracting volume resources has finished')

        return volumeResources

    def extract_volume_types(self, volume_type_ids):

        volume_type_dicts = []
        volumeTypeResources = []

        if not volume_type_ids:
            LOG.debug('Extract resources of all volume_types.')
            volume_type_dicts = self.cinder_api.volume_type_list(self.context)
        else:
            LOG.debug('Extract resources of volume_types: %s',
                      volume_type_ids)
            # remove duplicate volume_type
            volume_type_ids = {}.fromkeys(volume_type_ids).keys()
            for volume_type_id in volume_type_ids:
                try:
                    volume_type = \
                        self.cinder_api.get_volume_type(self.context,
                                                        volume_type_id)
                    volume_type_dicts.append(volume_type)
                except Exception as e:
                    msg = "VolumeType resource <%s> could not be found. %s" \
                            % (volume_type_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)

        for volume_type in volume_type_dicts:
            volume_type_id = volume_type['id']
            volume_type_res = self._collected_resources.get(volume_type_id)
            if volume_type_res:
                volumeTypeResources.append(volume_type_res)
                continue

            properties = {
                'name': volume_type['name']
            }
            dependencies = []
            # 2. check volume has qos or not, if having, build qos resource
            qos_id = volume_type.get('qos_specs_id', None)
            if qos_id:
                qos_driver = \
                    QosResource(
                        self.context,
                        collected_resources=self._collected_resources,
                        collected_parameters=self._collected_parameters,
                        collected_dependencies=self._collected_dependencies)

                qos_res = qos_driver.extract_qos(qos_id)
                properties['qos_specs_id'] = {'get_resource': qos_res.name}
                dependencies.append({'id': qos_res.id, 'name': qos_res.name,
                                     'name_in_template': '',
                                     'type': qos_res.type})
                self._collected_resources = \
                    qos_driver.get_collected_resources()
                self._collected_dependencies = \
                    qos_driver.get_collected_dependencies()

            if volume_type.get('extra_specs'):
                properties['metadata'] = volume_type['extra_specs']

            resource_type = "OS::Cinder::VolumeType"
            resource_name = 'volume_type_%d' % \
                self._get_resource_num(resource_type)

            volume_type_res = resource.Resource(resource_name, resource_type,
                                                volume_type_id,
                                                properties=properties)

            volume_type_dep = resource.ResourceDependency(
                                volume_type_id,
                                resource_name,
                                volume_type['name'],
                                resource_type,
                                dependencies=dependencies)

            self._collected_resources[volume_type_id] = volume_type_res
            self._collected_dependencies[volume_type_id] = volume_type_dep

            volumeTypeResources.append(volume_type_res)

        if volume_type_ids and not volumeTypeResources:
            msg = "VolumeType resource extracted failed, \
                    can't find the volume type with id of %s." % \
                    volume_type_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        return volumeTypeResources

    def extract_image(self, image_id):

        parameter_name = self._collected_parameters.get(image_id)

        if not parameter_name:
            parameter_name = "image_%d" % self._get_parameter_num()
            self._collected_parameters[image_id] = parameter_name

        return parameter_name


class Volume(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_volumes(self, volume_ids):
        if not volume_ids:
            _msg = 'No volume resource to extract.'
            LOG.info(_msg)
            return

        try:
            for volume_id in volume_ids:
                self.extract_volume(volume_id)
        except exception.ResourceExtractFailed:
            raise
        except exception.ResourceNotFound:
            raise
        except Exception as e:
            _msg = 'Create volume resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)

    def extract_volume(self, volume_id):

        LOG.debug('Create volume resource start: %s', volume_id)
        # 1.query volume info
        try:
            volume = self.cinder_api.get(self.context, volume_id)
        except Exception as e:
            msg = "Volume resource <%s> could not be found. %s" \
                     % (volume_id, unicode(e))
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        volume_id = volume.get('id')
        vol_state = volume.get('status', None)
        if vol_state not in resource_state.VOLUME_CLONE_STATE:
            LOG.error("Volume %(id)s state is %(state)s not available \
                      or in-use", {'id': volume_id, 'state': vol_state})
            raise exception.PlanCreateFailed
        v_res = self._collected_resources.get(volume_id)

        # check volume resource is existing or not
        if v_res:
            return v_res

        # 2. bulid volume resource
        properties = {
            'size': volume['size'],
            'name': volume['display_name'],
            'availability_zone': volume['availability_zone']
        }

        if volume.get('display_description'):
            properties['description'] = volume['display_description']
        vol_metadata = volume.get('volume_metadata', None)
        if vol_metadata:
            vol_metadata.pop('__hc_vol_id', None)
            vol_metadata.pop('__openstack_region_name', None)
            properties['metadata'] = vol_metadata
        resource_type = "OS::Cinder::Volume"
        resource_name = 'volume_%d' % self._get_resource_num(resource_type)
        volume_res = resource.Resource(resource_name, resource_type,
                                       volume_id, properties=properties)
        volume_dep = resource.ResourceDependency(volume_id,
                                                 resource_name,
                                                 volume['display_name'],
                                                 resource_type)

        self._collected_resources[volume_id] = volume_res
        self._collected_dependencies[volume_id] = volume_dep

        volume_res.add_extra_property('status', vol_state)
        volume_res.add_extra_property('copy_data', True)
        # 3. if volume has volume type, building volume type resource
        # and updating dependences
        volume_type_name = volume.get('volume_type')
        if volume_type_name:
            volume_types = self.cinder_api.volume_type_list(self.context)
            type_id = None

            for vtype in volume_types:
                if vtype['name'] == volume_type_name:
                    type_id = vtype['id']
                    break
            if type_id:
                type_driver = \
                    VolumeType(
                        self.context,
                        collected_resources=self._collected_resources,
                        collected_parameters=self._collected_parameters,
                        collected_dependencies=self._collected_dependencies)
                volume_type_res = type_driver.extract_volume_type(type_id)
                if volume_type_res:
                    t_name = volume_type_res.name
                    volume_res.add_property('volume_type',
                                            {'get_resource': t_name})
                    dep_res_name = volume_type_res.properties.get('name', '')
                    volume_dep.add_dependency(volume_type_res.id,
                                              volume_type_res.name,
                                              dep_res_name,
                                              volume_type_res.type)
                    self._collected_resources = \
                        type_driver.get_collected_resources()
                    self._collected_dependencies = \
                        type_driver.get_collected_dependencies()

        # 4. if volume has image or not, add image info to volume resource
        if volume['bootable'] == 'true' and \
           volume.get('volume_image_metadata'):
            image_id = volume['volume_image_metadata'].get('image_id')
            if image_id:
                image_para_name = self.extract_image(image_id)
                description = ("Image to use to boot server or volume")
                constraints = [{'custom_constraint': "glance.image"}]
                volume_res.add_parameter(image_para_name, description,
                                         default=image_id,
                                         constraints=constraints)
                volume_res.add_property('image',
                                        {'get_param': image_para_name})

        # 5.if volume in  consistency group, collect consistency group resource
        cg_id = volume.get('consistencygroup_id')
        if cg_id:
            from conveyor.resource.driver.consistencygroup import \
                ConsistencyGroup
            consisgroup_driver = \
                ConsistencyGroup(
                    self.context,
                    collected_resources=self._collected_resources,
                    collected_parameters=self._collected_parameters,
                    collected_dependencies=self._collected_dependencies)
            cons_res = consisgroup_driver.extract_consistency_group(cg_id)
            volume_res.add_property('consistencygroup_id',
                                    {'get_resource': cons_res.name})
            dep_res_name = cons_res.properties.get('name', '')
            volume_dep.add_dependency(cons_res.id,
                                      cons_res.name,
                                      dep_res_name,
                                      cons_res.type)
            self._collected_resources = \
                consisgroup_driver.get_collected_resources()
            self._collected_dependencies = \
                consisgroup_driver.get_collected_dependencies()

        LOG.debug('Create volume resource end: %s', volume_id)
        return volume_res

    def extract_image(self, image_id):

        parameter_name = self._collected_parameters.get(image_id)

        if not parameter_name:
            parameter_name = "image_%d" % self._get_parameter_num()
            self._collected_parameters[image_id] = parameter_name

        return parameter_name


class VolumeType(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_volume_types(self, volume_type_ids):
        if not volume_type_ids:
            _msg = 'Create volume type resource error: id is null.'
            LOG.error(_msg)
            raise exception.InvalidInput(reason=_msg)
        volume_type_res = []
        try:
            for volume_type_id in volume_type_ids:
                type_res = self.extract_volume_type(volume_type_id)
                volume_type_res.append(type_res)
        except exception.ResourceExtractFailed:
            raise
        except exception.ResourceNotFound:
            raise
        except Exception as e:
            _msg = 'Create volume type resource error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(_msg)

        return volume_type_res

    def extract_volume_type(self, volume_type_id):

        LOG.debug('Create volume type resource start: %s', volume_type_id)
        properties = {}
        dependencies = []
        # 1. query volume type info
        try:
            volume_type = self.cinder_api.get_volume_type(self.context,
                                                          volume_type_id)
        except Exception as e:
            msg = "VolumeType resource <%s> could not be found. %s" \
                    % (volume_type_id, unicode(e))
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)

        volume_type_id = volume_type['id']

        # check volume type resource is existing or not
        volume_type_res = self._collected_resources.get(volume_type_id)
        if volume_type_res:
            return volume_type_res

        # 2. check volume has qos or not, if having, build qos resource
        qos_id = volume_type.get('qos_specs_id')
        if qos_id:
            qos_driver = \
                QosResource(
                    self.context,
                    collected_resources=self._collected_resources,
                    collected_parameters=self._collected_parameters,
                    collected_dependencies=self._collected_dependencies)

            qos_res = qos_driver.extract_qos(qos_id)
            self._collected_resources = qos_driver.get_collected_resources()
            self._collected_dependencies = \
                qos_driver.get_collected_dependencies()
            properties['qos_specs_id'] = {'get_resource': qos_res.name}
            dependencies.append({'id': qos_res.id, 'name': qos_res.name,
                                 'name_in_template': '', 'type': qos_res.type})

        # 3. bulid volume type resource
        properties['name'] = volume_type.get('name')

        if volume_type.get('extra_specs'):
            properties['metadata'] = volume_type['extra_specs']

        resource_type = "OS::Cinder::VolumeType"
        resource_name = 'volume_type_%d' % \
            self._get_resource_num(resource_type)

        volume_type_res = resource.Resource(resource_name, resource_type,
                                            volume_type_id,
                                            properties=properties)

        type_dep = resource.ResourceDependency(volume_type_id,
                                               resource_name,
                                               volume_type['name'],
                                               resource_type,
                                               dependencies=dependencies)
        self._collected_resources[volume_type_id] = volume_type_res
        self._collected_dependencies[volume_type_id] = type_dep

        LOG.debug('Create volume type resource end: %s', volume_type_id)
        return volume_type_res


class QosResource(base.Resource):

    def __init__(self, context, collected_resources=None,
                 collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_qos(self, qos_id):

        LOG.debug('Create qos resource start: %s', qos_id)
        properties = {}
        # 1 check qos resource is existing or not
        qos_res = self._collected_resources.get(qos_id, None)
        if qos_res:
            LOG.debug('Create qos resource exist:  %s', qos_id)
            return qos_res
        # 2 query qos info
        try:
            qos_info = self.cinder_api.get_qos_specs(self.context, qos_id)
        except Exception as e:
            _msg = 'Create volume qos error: %s' % e
            LOG.error(_msg)
            raise exception.ResourceExtractFailed(reason=_msg)

        properties['specs'] = qos_info.get('specs')
        properties['name'] = qos_info.get('name')

        qos_type = "OS::Cinder::Qos"
        qos_name = 'CinderQos_%d' % self._get_resource_num(qos_type)

        qos_res = resource.Resource(qos_name, qos_type,
                                    qos_id, properties=properties)

        qos_dep = resource.ResourceDependency(qos_id, qos_name, '',
                                              qos_type)

        self._collected_resources[qos_id] = qos_res
        self._collected_dependencies[qos_id] = qos_dep

        LOG.debug('Create qos resource end: %s', qos_id)
        return qos_res
