'''
@author: g00357909
'''
from conveyor.api.common import ViewBuilder


class ViewBuilder(ViewBuilder):

    def types(self, type_list):
        types = []
        for type in type_list:
            types.append({"type": type})
        return {"types": types}
    


    
