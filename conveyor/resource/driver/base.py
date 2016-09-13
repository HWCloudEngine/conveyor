'''
@author: g00357909
'''

class resource(object):
    def __init__(self, context):
        self.context = context
        self._collected_resources = {}
        self._collected_parameters = {}
        self._collected_dependencies = {}
    
    def get_collected_resources(self):
        return self._collected_resources
    
    def get_collected_dependencies(self):
        return self._collected_dependencies
    
    def _get_resource_num(self, resource_type):
        num = -1
        for res in self._collected_resources.values():
            if resource_type == res.type:
                n = res.name.split('_')[-1]
                try:
                    n = int(n)
                    num = n if n > num else num
                except Exception:
                    pass
        return num + 1

    def _get_parameter_num(self):
        return len(self._collected_parameters)
    
    def _get_resource_by_name(self, name):
        for res in self.get_collected_resources().values():
            if res.name == name:
                return res
        return None