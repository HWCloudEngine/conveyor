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
import yaml

from oslo.config import cfg

from conveyor import exception
from conveyor.common import fileutils
from conveyor.i18n import _

template_opts = [
    cfg.IntOpt('max_template_size',
               default=524288,
               help='Maximum raw byte size of any template.')
]
CONF = cfg.CONF
CONF.register_opts(template_opts)


if hasattr(yaml, 'CSafeLoader'):
    yaml_loader = yaml.CSafeLoader
else:
    yaml_loader = yaml.SafeLoader

if hasattr(yaml, 'CSafeDumper'):
    yaml_dumper = yaml.CSafeDumper
else:
    yaml_dumper = yaml.SafeDumper


def _construct_yaml_str(self, node):
    # Override the default string handling function
    # to always return unicode objects
    return self.construct_scalar(node)

yaml_loader.add_constructor(u'tag:yaml.org,2002:str', _construct_yaml_str)
# Unquoted dates like 2013-05-23 in yaml files get loaded as objects of type
# datetime.data which causes problems in API layer when being processed by
# openstack.common.jsonutils. Therefore, make unicode string out of timestamps
# until jsonutils can handle dates.
yaml_loader.add_constructor(u'tag:yaml.org,2002:timestamp',
                            _construct_yaml_str)


def simple_parse(tmpl_str):
    try:
        tpl = json.loads(tmpl_str)
    except ValueError:
        try:
            tpl = yaml.load(tmpl_str, Loader=yaml_loader)
        except yaml.YAMLError as yea:
            raise ValueError(yea)
        else:
            if tpl is None:
                tpl = {}
    return tpl


def parse(tmpl_str):
    """Takes a string and returns a dict containing the parsed structure.

    This includes determination of whether the string is using the
    JSON or YAML format.
    """
    if len(tmpl_str) > CONF.max_template_size:
        msg = (_('Template exceeds maximum allowed size (%s bytes)') %
               CONF.max_template_size)
        raise exception.TemplateValidateFailed(message=msg)
    tpl = simple_parse(tmpl_str)
    if not isinstance(tpl, dict):
        raise ValueError(_('The template is not a JSON object '
                           'or YAML mapping.'))
    # Looking for supported version keys in the loaded template
    if not ('HeatTemplateFormatVersion' in tpl
            or 'heat_template_version' in tpl):
        raise ValueError(_("Template format version not found."))
    return tpl
