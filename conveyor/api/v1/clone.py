# Copyright 2011 Justin Santa Barbara
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

"""The conveyor api."""

import ast

import webob
from webob import exc

from oslo_log import log as logging
from conveyor.api import common
from conveyor.api.wsgi import wsgi
from conveyor import exception
from conveyor.i18n import _, _LI
from conveyor import utils

from conveyor.api.views import services as services_view
from conveyor.conveyoragentclient.v1 import client

LOG = logging.getLogger(__name__)


class CloneController(wsgi.Controller):
    """The Volumes API controller for the OpenStack API."""

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self.viewBulid = services_view.ViewBuilder()
        super(CloneController, self).__init__()

    def show(self, req, id):
        """Return data about the given resource."""
        LOG.debug("show is start.")
        context = req.environ['conveyor.context']
        stack = self.heat_api.get_stack(context, id)
        LOG.debug("Heat test: %s", stack)

    def delete(self, req, id):
        """Delete resource."""
        LOG.debug("delete is start.")
        return

    def index(self, req):
        """Returns a summary list of resource."""
        LOG.debug("index is start.")
        return

    def detail(self, req):
        """Returns a detailed list of resource."""
        LOG.debug("Detail is start.")
        return

    def create(self, req, body):
        """Creates a new resource."""
        pass


    def update(self, req, id, body):
        """Update a resource."""
        context = req.environ['conveyor.context']

        pass


def create_resource(ext_mgr):
    return wsgi.Resource(CloneController(ext_mgr))

