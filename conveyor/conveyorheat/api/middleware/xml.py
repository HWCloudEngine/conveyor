# Copyright (c) 2014, Huawei Technologies Co., Ltd
# All rights reserved.


from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.common import wsgi


class XmlMiddleware(wsgi.Middleware):

    def process_request(self, req):
        if req.content_type == 'application/xml':
            raise exception.ValidationError()
