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

from debtcollector import removals
from conveyor.conveyorheat.api.middleware import fault
from conveyor.conveyorheat.api.middleware.resource_filter import resource_filter as rs_filter
from conveyor.conveyorheat.api.middleware import ssl
from conveyor.conveyorheat.api.middleware import version_negotiation as vn
from conveyor.conveyorheat.api.middleware.xml import XmlMiddleware
from conveyor.conveyorheat.api.openstack import versions


def version_negotiation_filter(app, conf, **local_conf):
    return vn.VersionNegotiationFilter(versions.Controller, app,
                                       conf, **local_conf)


def faultwrap_filter(app, conf, **local_conf):
    return fault.FaultWrapper(app)


@removals.remove(message='Use oslo_middleware.http_proxy_to_wsgi instead.',
                 version='6.0.0', removal_version='8.0.0')
def sslmiddleware_filter(app, conf, **local_conf):
    return ssl.SSLMiddleware(app)


def xml_wrap_filter(app, conf, **local_conf):
    return XmlMiddleware(app)


def resource_filter(app, conf, **local_conf):
    return rs_filter.ResourceMiddleware(app)
