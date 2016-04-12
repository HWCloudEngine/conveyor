'''
@author: g00357909
'''
from conveyor import exception
from conveyor import volume

from conveyor.resource import resource
from conveyor.resource.driver import base
from conveyor.common import log as logging
LOG = logging.getLogger(__name__)


class VolumeResource(base.resource):
    
    def __init__(self, context, collected_resources=None,
                collected_parameters=None, collected_dependencies=None):
        self.context = context
        self.cinder_api = volume.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_volumes(self, volume_ids):
        
        volume_objs = []
        volumeResources = []
            
        if not volume_ids:
            LOG.info('Extract resources of all volumes.')
            volume_objs = self.cinder_api.volume_list(self.context)
        else:
            LOG.info('Extract resources of volumes: %s', volume_ids)
            #remove duplicate volume
            volume_ids = {}.fromkeys(volume_ids).keys()
            for volume_id in volume_ids:
                try:
                    volume = self.cinder_api.get_volume(self.context, volume_id)
                    volume_objs.append(volume)
                except Exception:
                    LOG.error("Volume resource %s could not be found.", volume_id)
                    raise exception.ResourceNotFound(resource_type='Volume', resource_id=volume_id)

        for volume in volume_objs:
            volume_id = getattr(volume, 'id', '')
            volume_res = self._collected_resources.get(volume_id)
            if volume_res:
                volumeResources.append(volume_res)
                continue
            
            properties = {
                'size': getattr(volume, 'size', ''),
                'availability_zone': getattr(volume, 'availability_zone', '')
            }
            
            if getattr(volume, 'name', ''):
                properties['name'] = getattr(volume, 'name', '') 
            if getattr(volume, 'description', ''):
                properties['description'] = getattr(volume, 'description', '')
            if getattr(volume, 'metadata', ''):
                properties['metadata'] = getattr(volume, 'metadata', '')            
            
            resource_type = "OS::Cinder::Volume"
            resource_name = 'volume_%d' % self._get_resource_num(resource_type)
            volume_res = resource.Resource(resource_name, resource_type,
                                volume_id, properties=properties)
            volume_dep = resource.ResourceDependency(volume_id, getattr(volume, 'name', ''), 
                                                       resource_name, resource_type)
            
            volume_type_name = getattr(volume, 'volume_type', '')
            if volume_type_name:
                volume_types = self.cinder_api.volume_type_list(self.context)
                volume_type_id = None
                
                for vtype in volume_types:
                    if getattr(vtype, 'name', '') == volume_type_name:
                        volume_type_id = getattr(vtype, 'id', '')
                        break
                if volume_type_id:
                    volume_type_res = self.extract_volume_types([volume_type_id])
                    if volume_type_res:
                        volume_res.add_property('volume_type', {'get_resource': volume_type_res[0].name})
                        volume_dep.add_dependency(volume_type_res[0].name)

            if getattr(volume, 'bootable', '') == 'true' and getattr(volume, 'volume_image_metadata', {}):
                image_id = getattr(volume, 'volume_image_metadata', {}).get('image_id', '')
                if image_id:
                    image_para_name = self.extract_image(image_id)
                    description = ("Image to use to boot server or volume")
                    constraints = [{'custom_constraint': "glance.image"}]
                    volume_res.add_parameter(image_para_name, description,
                                           default=image_id, constraints=constraints)
                    volume_res.add_property('image', {'get_param': image_para_name})
                
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
        
        volume_type_objs = []
        volumeTypeResources = []
            
        if not volume_type_ids:
            LOG.debug('Extract resources of all volume_types.')
            volume_type_objs = self.cinder_api.volume_type_list(self.context)
        else:
            LOG.debug('Extract resources of volume_types: %s', volume_type_ids)
            #remove duplicate volume_type
            volume_type_ids = {}.fromkeys(volume_type_ids).keys()
            for volume_type_id in volume_type_ids:
                try:
                    volume_type = self.cinder_api.get_volume_type(self.context, volume_type_id)
                    volume_type_objs.append(volume_type)
                except Exception:
                    LOG.error("VolumeType resource %s could not be found.", volume_type_id)
                    raise exception.ResourceNotFound(resource_type='VolumeType', resource_id=volume_type_id)

        for volume_type in volume_type_objs:
            volume_type_id = getattr(volume_type, 'id', '')
            volume_type_res = self._collected_resources.get(volume_type_id)
            if volume_type_res:
                volumeTypeResources.append(volume_type_res)
                continue
            
            properties = {
                'name': getattr(volume_type, 'name', ''),
            }
            
            if getattr(volume_type, 'extra_specs', {}):   
                properties['metadata'] = getattr(volume_type, 'extra_specs', {}) 

            resource_type = "OS::Cinder::VolumeType"
            resource_name = 'volume_type_%d' % self._get_resource_num(resource_type)

            volume_type_res = resource.Resource(resource_name, resource_type,
                                volume_type_id, properties=properties)
             
            volume_type_dep = resource.ResourceDependency(volume_type_id, getattr(volume_type, 'name', ''), 
                                                       resource_name, resource_type)
            
            self._collected_resources[volume_type_id] = volume_type_res
            self._collected_dependencies[volume_type_id] = volume_type_dep
            
            volumeTypeResources.append(volume_type_res)
            
        if volume_type_ids and not volumeTypeResources:
            msg = "VolumeType resource extracted failed, \
                    can't find the volume type with id of %s." % volume_type_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return volumeTypeResources
    
    
#TO DO qos_specs
#     def _build_qos_specs(self, build_all=False):
#         qos_specs = self.cinder_api.qos_specs_list(self.context)
#         
#         for qos in qos_specs:
#             qos_id = getattr(qos, 'id')
#             
#             qos_resources = self._collected_resources.get(qos_id)
#             
#             if qos_resources:
#                 continue
#             
#             associations = self.cinder_api.get_qos_associations(self.context, qos_id)
#             
#             properties = {
#                           }
#             
#             for volume_type in associations:
#                 type_id = getattr(volume_type, 'id')
#                 volume_type_resource = self._collected_resources.get(type_id)

    def extract_image(self, image_id):
        
        parameter_name = self._collected_parameters.get(image_id)
        
        if not parameter_name:
            parameter_name = "image_%d" % self._get_parameter_num()
            self._collected_parameters[image_id] = parameter_name
            
        return parameter_name

