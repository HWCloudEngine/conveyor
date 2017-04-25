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

import json

from webob import exc

from conveyor.conveyorheat.common import environment_format
from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.common import template_format
from conveyor.conveyorheat.common import urlfetch
from conveyor.conveyorheat.common import wsgi

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import _cache_handler

LOG = logging.getLogger(__name__)


supported_resources = []
catch_files = {}


class UnsupportedResource(Exception):
    def __init__(self, resource_type):
        self.resource_type = resource_type

    def __str__(self):
        return 'Unsupported resource type: %s' % self.resource_type


class ResourceMiddleware(wsgi.Middleware):
    def process_request(self, req):
        if not cfg.CONF.FusionSphere.filter_resource:
            # if not support filter resources, do nothing and just return.
            return

        try:
            if req.body:
                ResourceFilter(req.body)()
        except UnsupportedResource as e:
            raise exc.HTTPBadRequest(_('Unsupported resource type: %s') %
                                     e.resource_type)
        except Exception:
            LOG.error(_('Internal service error.'))


class ResourceFilter(object):
    PARAMS = (
        PARAM_TEMPLATE,
        PARAM_TEMPLATE_URL,
        PARAM_ENVIRONMENT,
        PARAM_FILES,
    ) = (
        'template',
        'template_url',
        'environment',
        'files',
    )

    ENV_PARAMS = (
        RESOURCE_REG
    ) = (
        'resource_registry'
    )

    def __init__(self, data):
        self.data = json.loads(data)
        self.resource_registry = {}

    def __call__(self, *args, **kwargs):
        load_supported_resources()
        self.load_env()
        templ = self.get_template()
        self.check_template(templ)

    def load_env(self):
        if self.PARAM_ENVIRONMENT in self.data:
            env_data = self.data[self.PARAM_ENVIRONMENT]
            if isinstance(env_data, dict):
                env = env_data
            else:
                env = environment_format.parse(env_data)

            self.resource_registry = env.get(self.RESOURCE_REG, {})

    def get_template(self):
        if self.PARAM_TEMPLATE in self.data:
            template_data = self.data[self.PARAM_TEMPLATE]
            if isinstance(template_data, dict):
                return template_data
        elif self.PARAM_TEMPLATE_URL in self.data:
            url = self.data[self.PARAM_TEMPLATE_URL]
            LOG.debug('TemplateUrl %s' % url)
            try:
                template_data = urlfetch.get(url)
            except IOError as ex:
                err_reason = _('Could not retrieve template: %s') % ex
                raise exc.HTTPBadRequest(err_reason)
        else:
            raise exc.HTTPBadRequest(_("No template specified"))

        return template_format.parse(template_data)

    def check_template(self, templ):
        if isinstance(templ, dict):
            templ_dict = templ
        else:
            templ_dict = template_format.parse(templ)

        resources = templ_dict.get('Resources') or templ_dict.get('resources')
        if resources:
            for res in resources.values():
                res_type = res.get('Type') or res.get('type')
                res_type = self.get_env_res(res_type)
                if self.is_file(res_type):
                    self.check_template(self.get_file(res_type))
                else:
                    check_res_type(res_type)

    def get_env_res(self, res_type):
        if res_type in self.resource_registry.keys():
            return self.resource_registry.get(res_type)

        return res_type

    def is_file(self, key):
        return (self.PARAM_FILES not in self.data or
                key in self.data[self.PARAM_FILES])

    def get_file(self, key):
        if self.PARAM_FILES in self.data:
            return self.data[self.PARAM_FILES].get(key)


def load_supported_resources():
    global supported_resources
    reloaded, data = _cache_handler.read_cached_file(
        catch_files, cfg.CONF.FusionSphere.support_resources_conf_file)
    if reloaded:
        supported_resources = json.loads(data)


def check_res_type(res_type):
    global supported_resources
    load_supported_resources()
    if res_type not in supported_resources:
        LOG.error(_('Unsupported resource type: %s') % res_type)
        raise UnsupportedResource(res_type)
