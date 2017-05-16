# Copyright 2011 OpenStack Foundation
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

"""RequestContext: context for requests that persist through all of fs_gateway."""

import copy
import uuid

import six

from keystoneclient import access
from keystoneclient import auth
from keystoneclient.auth.identity import access as access_plugin
from keystoneclient.auth.identity import v3
from keystoneclient.auth import token_endpoint
from oslo_config import cfg

import exception
from conveyor.i18n import _
from conveyor.i18n import _LE
from conveyor.i18n import _LW
from conveyor.common import local
from oslo_log import log as logging
from oslo_utils import timeutils
from conveyor.db import api as db_api
from conveyor.conveyorheat.engine import clients
from conveyor.conveyorheat.common import endpoint_utils


LOG = logging.getLogger(__name__)

TRUSTEE_CONF_GROUP = 'trustee'


def generate_request_id():
    return 'req-' + str(uuid.uuid4())


class RequestContext(object):
    """Security context and request information.

    Represents the user taking a given action within the system.

    """

    def __init__(self, user_id, project_id, is_admin=None, read_deleted="no",
                 roles=None, remote_address=None, timestamp=None,
                 request_id=None, auth_token=None, overwrite=True,
                 quota_class=None, user_name=None, project_name=None,
                 service_catalog=None, instance_lock_checked=False,
                 auth_token_info=None, auth_url=None, tenant_id=None,
                 show_deleted=False, region_name=None, auth_plugin=None,
                 trust_id=None, trusts_auth_plugin=None, password=None,
                 user_domain_id=None, iam_assume_token=None, **kwargs):
        """:param read_deleted: 'no' indicates deleted records are hidden,
                'yes' indicates deleted records are visible,
                'only' indicates that *only* deleted records are visible.


           :param overwrite: Set to False to ensure that the greenthread local
                copy of the index is not overwritten.

           :param kwargs: Extra arguments that might be present, but we ignore
                because they possibly came in from older rpc messages.
        """
        if kwargs:
            LOG.warn(_('Arguments dropped when creating context: %s') %
                    str(kwargs))

        self.user_id = user_id
        self.project_id = project_id
        self.roles = roles or []
        self.read_deleted = read_deleted
        self.remote_address = remote_address
        if not timestamp:
            timestamp = timeutils.utcnow()
        if isinstance(timestamp, six.string_types):
            timestamp = timeutils.parse_strtime(timestamp)
        self.timestamp = timestamp
        if not request_id:
            request_id = generate_request_id()
        self.request_id = request_id
        self.auth_token = auth_token
        self.auth_token_info = auth_token_info
        self.auth_url = auth_url
        self.tenant_id = tenant_id
        self.show_deleted = show_deleted
        self._clients = None
        self.username = user_name
        self.region_name = region_name
        self._auth_plugin = auth_plugin
        self.trust_id = trust_id
        self._trusts_auth_plugin = trusts_auth_plugin
        self.password = password
        self.user_domain = user_domain_id
        self.iam_assume_token = iam_assume_token

        if service_catalog:
            # Only include required parts of service_catalog
            self.service_catalog = [s for s in service_catalog
                if s.get('type') in ('identity', 'compute','volume',
                                      'volumev2', 'network', 'key-manager', 'orchestration')]
        else:
            # if list is empty or none
            self.service_catalog = []

        self.instance_lock_checked = instance_lock_checked

        # NOTE(markmc): this attribute is currently only used by the
        # rs_limits turnstile pre-processor.
        # See https://lists.launchpad.net/openstack/msg12200.html
        self.quota_class = quota_class
        self.user_name = user_name
        self.project_name = project_name
        self.is_admin = is_admin
        self._session = None
        # self.session = db_api.get_session()
        if overwrite or not hasattr(local.store, 'context'):
            self.update_store()

    @property
    def keystone_v3_endpoint(self):
        if self.auth_url:
            return self.auth_url.replace('v2.0', 'v3')
        else:
            auth_uri = endpoint_utils.get_auth_uri()
            if auth_uri:
                return auth_uri
            else:
                LOG.error('Keystone API endpoint not provided. Set '
                          'auth_uri in section [clients_keystone] '
                          'of the configuration file.')
                raise exception.AuthorizationFailure()

    @property
    def trusts_auth_plugin(self):
        if self._trusts_auth_plugin:
            return self._trusts_auth_plugin

        self._trusts_auth_plugin = auth.load_from_conf_options(
            cfg.CONF, TRUSTEE_CONF_GROUP, trust_id=self.trust_id)

        if self._trusts_auth_plugin:
            return self._trusts_auth_plugin

        LOG.warning(_LW('Using the keystone_authtoken user as the conveyorheat '
                        'trustee user directly is deprecated. Please add the '
                        'trustee credentials you need to the %s section of '
                        'your heat.conf file.') % TRUSTEE_CONF_GROUP)

        cfg.CONF.import_group('keystone_authtoken',
                              'keystonemiddleware.auth_token')

        trustee_user_domain = 'default'
        if 'user_domain_id' in cfg.CONF.keystone_authtoken:
            trustee_user_domain = cfg.CONF.keystone_authtoken.user_domain_id

        self._trusts_auth_plugin = v3.Password(
            username=cfg.CONF.keystone_authtoken.admin_user,
            password=cfg.CONF.keystone_authtoken.admin_password,
            user_domain_id=trustee_user_domain,
            auth_url=self.keystone_v3_endpoint,
            trust_id=self.trust_id)
        return self._trusts_auth_plugin

    def _create_auth_plugin(self):
        if self.auth_token_info:
            auth_ref = access.AccessInfo.factory(body=self.auth_token_info,
                                                 auth_token=self.auth_token)
            return access_plugin.AccessInfoPlugin(
                auth_url=self.keystone_v3_endpoint,
                auth_ref=auth_ref)

        if self.auth_token:
            # FIXME(jamielennox): This is broken but consistent. If you
            # only have a token but don't load a service catalog then
            # url_for wont work. Stub with the keystone endpoint so at
            # least it might be right.
            return token_endpoint.Token(endpoint=self.keystone_v3_endpoint,
                                        token=self.auth_token)

        if self.password:
            return v3.Password(username=self.username,
                               password=self.password,
                               project_id=self.tenant_id,
                               user_domain_id=self.user_domain,
                               auth_url=self.keystone_v3_endpoint)

        LOG.error(_LE("Keystone v3 API connection failed, no password "
                      "trust or auth_token!"))
        raise exception.AuthorizationFailure()

    @property
    def auth_plugin(self):
        if not self._auth_plugin:
            if self.trust_id:
                self._auth_plugin = self.trusts_auth_plugin
            else:
                self._auth_plugin = self._create_auth_plugin()

        return self._auth_plugin

    @property
    def session(self):
        if self._session is None:
            self._session = db_api.get_session()
        return self._session

    @property
    def clients(self):
        if self._clients is None:
            self._clients = clients.Clients(self)
        return self._clients

    def _get_read_deleted(self):
        return self._read_deleted

    def _set_read_deleted(self, read_deleted):
        if read_deleted not in ('no', 'yes', 'only'):
            raise ValueError(_("read_deleted can only be one of 'no', "
                               "'yes' or 'only', not %r") % read_deleted)
        self._read_deleted = read_deleted

    def _del_read_deleted(self):
        del self._read_deleted

    read_deleted = property(_get_read_deleted, _set_read_deleted,
                            _del_read_deleted)

    def update_store(self):
        local.store.context = self

    def to_dict(self):
        return {'user_id': self.user_id,
                'project_id': self.project_id,
                'is_admin': self.is_admin,
                'read_deleted': self.read_deleted,
                'roles': self.roles,
                'remote_address': self.remote_address,
                'timestamp': timeutils.strtime(self.timestamp),
                'request_id': self.request_id,
                'auth_token': self.auth_token,
                'quota_class': self.quota_class,
                'user_name': self.user_name,
                'service_catalog': self.service_catalog,
                'project_name': self.project_name,
                'instance_lock_checked': self.instance_lock_checked,
                'tenant': self.tenant,
                'user': self.user,
                'auth_token_info': self.auth_token_info,
                'auth_url': self.auth_url,
                'tenant_id': self.tenant_id,
                'show_deleted': self.show_deleted,
                'iam_assume_token': self.iam_assume_token}

    @classmethod
    def from_dict(cls, values):
        values.pop('user', None)
        values.pop('tenant', None)
        return cls(**values)

    def elevated(self, read_deleted=None, overwrite=False):
        """Return a version of this context with admin flag set."""
        context = copy.copy(self)
        context.is_admin = True

        if 'admin' not in context.roles:
            context.roles.append('admin')

        if read_deleted is not None:
            context.read_deleted = read_deleted

        return context

    # NOTE(sirp): the openstack/common version of RequestContext uses
    # tenant/user whereas the Nova version uses project_id/user_id. We need
    # this shim in order to use context-aware code from openstack/common, like
    # logging, until we make the switch to using openstack/common's version of
    # RequestContext.
    @property
    def tenant(self):
        return self.project_id

    @property
    def user(self):
        return self.user_id


def get_admin_context(read_deleted="no"):
    return RequestContext(user_id=None,
                          project_id=None,
                          is_admin=True,
                          read_deleted=read_deleted,
                          overwrite=False)


def is_user_context(context):
    """Indicates if the request context is a normal user."""
    if not context:
        return False
    if context.is_admin:
        return False
    if not context.user_id or not context.project_id:
        return False
    return True


def require_admin_context(ctxt):
    """Raise exception.AdminRequired() if context is an admin context."""
    if not ctxt.is_admin:
        raise exception.AdminRequired()


def require_context(ctxt):
    """Raise exception.Forbidden() if context is not a user or an
    admin context.
    """
    if not ctxt.is_admin and not is_user_context(ctxt):
        raise exception.Forbidden()


def authorize_project_context(context, project_id):
    """Ensures a request has permission to access the given project."""
    if is_user_context(context):
        if not context.project_id:
            raise exception.Forbidden()
        elif context.project_id != project_id:
            raise exception.Forbidden()


def authorize_user_context(context, user_id):
    """Ensures a request has permission to access the given user."""
    if is_user_context(context):
        if not context.user_id:
            raise exception.Forbidden()
        elif context.user_id != user_id:
            raise exception.Forbidden()


def authorize_quota_class_context(context, class_name):
    """Ensures a request has permission to access the given quota class."""
    if is_user_context(context):
        if not context.quota_class:
            raise exception.Forbidden()
        elif context.quota_class != class_name:
            raise exception.Forbidden()
