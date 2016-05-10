'''
@author: g00357909
'''
import time
import six

from conveyor.common import timeutils
from webob import exc
from conveyor.i18n import _
from conveyor.common import uuidutils
from conveyor.common import template_format
from conveyor.api.wsgi import wsgi
from conveyor.common import log as logging
from conveyor import exception
from conveyor.resource import api as resource_api

LOG = logging.getLogger(__name__)


class Controller(wsgi.Controller):
    """The plan API controller for the conveyor API."""

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self._resource_api = resource_api.ResourceAPI()
        super(Controller, self).__init__()

    def show(self, req, id):
        LOG.debug("Get plan with id of %s.", id)
        
        if not uuidutils.is_uuid_like(id):
            msg = _("Invalid id provided, id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        
        try:
            plan = self._resource_api.get_plan_by_id(context, id)
            return {"plan": plan}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))
#         except exception.PlanNotFound:
#             msg = _("The plan %s could not be found" % id)
#             LOG.error(msg)
#             raise exc.HTTPInternalServerError(explanation=msg)
        

    def create(self, req, body):
        LOG.debug("Create a clone or migrate plan.")
        
        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        params = body["plan"]
        
        resources = []
        
        if not params.get('type') or not params.get('resources'):
            msg = _('The body should contain type and resources information.')
            raise exc.HTTPBadRequest(explanation=msg)
        
        for res in params.get('resources', []):
            if not isinstance(res, dict):
                msg = _("Every resource must be a dict with id and type keys.")
                raise exc.HTTPBadRequest(explanation=msg)
            
            res_id = res.get('id')
            res_type = res.get('type')
            if not res_id or not res_type:
                msg = _('Type or id is empty')
                raise exc.HTTPBadRequest(explanation=msg)
            resources.append({'id': res_id, 'type': res_type})
        
        if not resources:
            msg = _('No vaild resource, please check the types and ids')
            raise exc.HTTPBadRequest(explanation=msg)
        
        try:
            plan_id, dependencies = self._resource_api.create_plan(context, params.get('type'), resources)
            return {'plan': {'plan_id': plan_id, 'original_dependencies': dependencies}}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))
#         except exception.ResourceTypeNotSupported as e:
#             LOG.error(e.msg)
#             raise exc.HTTPBadRequest(explanation=e.msg)
#         except exception.ResourceExtractFailed as e:
#             LOG.error(e.msg)
#             raise exc.HTTPInternalServerError(explanation=e.msg)

    def create_plan_by_template(self, req, body):
        
        LOG.debug("Create a plan by template")
        
        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']

        tpl_param = body['plan'].get('template')
        if not tpl_param:
            msg = _('No template found in body.')
            raise exc.HTTPBadRequest(explanation=msg)

        template = self._convert_template_to_json(tpl_param)
        
        expire_time = template.get('expire_time')
        plan_type = template.get('plan_type')
        
        if not expire_time or not plan_type:
            msg = _("Template must have 'expire_time' and 'plan_type' field.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        expire_time = timeutils.parse_isotime(expire_time)
        if timeutils.is_older_than(expire_time, 0):
            msg = _("Template is out of time.")
            raise exc.HTTPBadRequest(explanation=msg)
            
        try:
            plan = self._resource_api.create_plan_by_template(context, template)
            return {"plan": plan}
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


    def _convert_template_to_json(self, template):
        if isinstance(template, dict):
            return template
        elif isinstance(template, six.string_types):
            LOG.debug("Convert template from string to map")
            return template_format.parse(template)
        else:
            msg = _("Template must be string or map.")
            raise exc.HTTPBadRequest(explanation=msg)


    def delete(self, req, id):
        LOG.debug("Delete plan <%s>.", id)

        if not uuidutils.is_uuid_like(id):
            msg = _("Invalid id provided, id must be uuid.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        
        try:
            self._resource_api.delete_plan(context, id)
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))
#         except exception.PlanNotFound:
#             msg = _("Delete failed. The plan %s could not be found" % id)
#             raise exc.HTTPInternalServerError(explanation=msg)


    @wsgi.response(202)
    @wsgi.action('update_plan_resources')
    def _update_plan_resources(self, req, id, body):
        """Update resource of specific plan."""
        
        if not self.is_valid_body(body, 'update_plan_resources'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        update_values = body['update_plan_resources'].get('resources')
        
        if not update_values:
            msg = _('No resources found in body.')
            raise exc.HTTPBadRequest(explanation=msg)
        
        LOG.debug("Update resource of plan <%s> with values: %s", id, update_values)

        try:
            self._resource_api.update_plan_resources(context, id, update_values)
            #self._resource_api.update_plan(context, id,
            #                               {"updated_resources": update_values})
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))


    def update(self, req, id, body):
        """Update a plan."""
        LOG.debug("Update a plan.")
        
        if not self.is_valid_body(body, 'plan'):
            msg = _("Incorrect request body format.")
            raise exc.HTTPBadRequest(explanation=msg)
        
        context = req.environ['conveyor.context']
        update_values = body['plan']

        try:
            self._resource_api.update_plan(context, id, update_values)
        except Exception as e:
            LOG.error(unicode(e))
            raise exc.HTTPInternalServerError(explanation=unicode(e))
        
        
    def detail(self, req):
        LOG.debug("Get all plans.")
        search_opts = {}
        search_opts.update(req.GET)
        context = req.environ['conveyor.context']
        #limit, marker = common.get_limit_and_marker(req)
        plans = self._resource_api.get_plans(context, search_opts=search_opts)
        
        return {"plans": plans}


def create_resource(ext_mgr):
    return wsgi.Resource(Controller(ext_mgr))
