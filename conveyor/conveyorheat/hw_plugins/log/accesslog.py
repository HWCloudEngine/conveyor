#
# Copyright 2016 Huawei Technologies Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import six
import sys
import time
import urllib
import urlparse

from keystoneclient.common import cms
from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslo_utils import uuidutils

import webob.dec

from conveyor.conveyorheat.common import wsgi
from conveyor.conveyorheat.hw_plugins.log import HWExtend
import log

reload(sys)
sys.setdefaultencoding('utf-8')
log.init('heat-api')
APACHE_TIME_FORMAT = '%d/%b/%Y:%H:%M:%S'
APACHE_LOG_FORMAT = (
    '%(remote_addr)s - %(remote_user)s [%(datetime)s] "%(method)s %(url)s '
    '%(http_version)s" %(status)s %(content_length)s')

DRM_LOG_FORMAT = ('%(remote_addr)s - %(remote_user)s - %(token_id)s '
                  '[%(request_datetime)s][%(response_datetime)s]'
                  ' %(method)s %(url)s %(http_version)s %(status)s'
                  ' %(content_length)s %(request_body)s -')

CTS_LOG_FORMAT = ('%(remote_addr)s - %(remote_user)s - %(token_id)s '
                  '[%(request_datetime)s][%(response_datetime)s]'
                  ' %(method)s %(url)s %(http_version)s %(status)s'
                  ' %(content_length)s %(request_body)s - %(opt_time)s'
                  ' %(opt_domainname)s %(opt_domainid)s '
                  ' %(opt_project_id)s %(opt_username)s %(opt_userid)s'
                  ' %(opt_service_type)s %(opt_resourectype)s'
                  ' %(opt_resourcename)s %(opt_resourceid)s'
                  ' %(opt_tracename)s %(opt_trace_rating)s'
                  ' %(opt_trace_type)s %(opt_api_version)s'
                  ' %(opt_source_ip)s')

ENCODED_KEYS = ('Signature', 'SignatureMethod', 'AWSAccessKeyId')


def encode_url(url):
    try:
        pr = urlparse.urlparse(url)
        query = dict(urlparse.parse_qsl(pr.query))
    except Exception:
        return url

    # replace sensitive message info in url such as Signature, SignatureMethod
    # and AWSAccessKeyId
    for key in ENCODED_KEYS:
        try:
            if query[key]:
                query[key] = '***'
        except KeyError:
            pass

    parameter_list = list(pr)
    parameter_list[4] = urllib.urlencode(query)

    return urlparse.ParseResult(*parameter_list).geturl()


def parse_access_key(url):
    try:
        pr = urlparse.urlparse(url)
        query = dict(urlparse.parse_qsl(pr.query))
    except Exception:
        return None

    return query.get('AWSAccessKeyId', None)


def get_dict_key(from_dict, attr1, default):
    try:
        return from_dict[attr1]
    except Exception:
        return default


def get_info_noexcept(from_dict, attr1, attr2=None, attr3=None):
    if get_dict_key(from_dict, attr1, None) is None:
        return None
    else:
        if attr2 is not None:
            if get_dict_key(from_dict[attr1], attr2, None) is None:
                return None
            else:
                if attr3 is not None:
                    return get_dict_key(from_dict[attr1][attr2],
                                        attr3, None)
                else:
                    return get_dict_key(from_dict[attr1], attr2,
                                        None)
        else:
            return get_dict_key(from_dict, attr1, None)


def check_data_type(check_item, data):
    if check_item == 'resource_id':
        return uuidutils.is_uuid_like(data)
    elif check_item == 'action':
        return isinstance(data, six.string_types)
    else:
        return False


def get_the_match_path(path_pattern, path_pattern_diff, path_item):
    init_match = []
    if len(path_pattern) > 1:
        for i in range(0, len(path_pattern)):
            init_match.append(i)
        for i in range(0, len(path_item)):
            if not path_pattern_diff[i]:
                for j in range(0, len(path_pattern)):
                    if not check_data_type(path_pattern[j][i],
                                           path_item[i]):
                        init_match.remove(j)
    else:
        init_match.append(0)
    return init_match


def get_info_from_resource(path_item, resource_map,
                           resource_trace_map, resource_map_diff):
    resource_info = {}
    trace_info = {}
    if len(path_item) not in resource_map.keys():
        return resource_info, trace_info
    if len(resource_map[len(path_item)]) > 1:
        # here have multi match
        match = get_the_match_path(resource_map[len(path_item)],
                                   resource_map_diff[
                                       len(path_item)],
                                   path_item)[0]
        match_path = resource_map[len(path_item)][match]
        match_trace = resource_trace_map[len(path_item)][match]
    else:
        match_path = resource_map[len(path_item)][0]
        match_trace = resource_trace_map[len(path_item)][0]
    for i in range(0, len(match_path)):
        resource_info[str(match_path[i])] = path_item[i]
    trace_name = match_trace % resource_info

    def underline_to_camel(underline_format):
        camel_format = ''
        if isinstance(underline_format, str):
            for _s_ in underline_format.split('_'):
                camel_format += _s_.capitalize()
        return camel_format

    trace_name = underline_to_camel(trace_name)
    trace_name = trace_name[0].lower() + trace_name[1:]
    trace_info['trace_name'] = trace_name
    return resource_info, trace_info


def get_post_resource_id(response_body, default_id):
    if 'id' in response_body.keys() and uuidutils. \
            is_uuid_like(response_body['id']):
        return response_body['id']
    else:
        for key in response_body.keys():
            if uuidutils.is_uuid_like(get_dict_key(
                    response_body[key], 'id', None)):
                return get_dict_key(response_body[key],
                                    'id', default_id)
    return default_id


class AccessLogMiddleware(wsgi.Middleware):
    """Writes an access log to INFO."""

    @webob.dec.wsgify
    def __call__(self, request):
        now = timeutils.utcnow()
        reqBody = "-"
        if ('xml' in str(request.content_type) or
                'json' in str(request.content_type)):
            if (request.content_length is not None and
                    request.content_length < 10240):
                reqBody = str(request.body) or '-'
                if HWExtend.hasSensitiveStr(reqBody):
                    reqBody = '-'
        data = {
            'remote_addr': request.remote_addr,
            'remote_user': request.remote_user or '-',
            'token_id': "None",
            'request_datetime': '%s' % now.strftime(APACHE_TIME_FORMAT),
            'response_datetime': '%s' % now.strftime(APACHE_TIME_FORMAT),
            'method': request.method,
            'url': request.url,
            'http_version': request.http_version,
            'status': 500,
            'content_length': '-',
            'opt_time': '-',
            'opt_domainname': '-',
            'opt_domainid': '-',
            'opt_project_id': '-',
            'opt_username': '-',
            'opt_userid': '-',
            'opt_service_type': '-',
            'opt_resourectype': '-',
            'opt_resourcename': '-',
            'opt_resourceid': '-',
            'opt_tracename': '-',
            'opt_trace_rating': '-',
            'opt_trace_type': '-',
            'opt_api_version': '-',
            'opt_source_ip': '-',
            'opt_response_id': '-',
            'request_body': reqBody}
        token = ''
        try:
            token = request.headers['X-Auth-Token']
            token = HWExtend.b64encodeToken(token)
        except Exception:
            token = "-"
        try:
            response = request.get_response(self.application)
            data['status'] = response.status_int
            data['content_length'] = response.content_length or '-'
        finally:
            # must be calculated *after* the application has been called
            now = timeutils.utcnow()
            data['token_id'] = token
            if "GET" in data['method'] and "/tokens/" in data['url']:
                Pos = data['url'].find("tokens") + 7
                logToken = data['url'][Pos:Pos + 32]
                encodedToken = HWExtend.b64encodeToken(logToken)
                data['url'] = data['url'].replace(logToken, encodedToken)
            # timeutils may not return UTC, so we can't hardcode +0000
            data['response_datetime'] = ('%s' %
                                         (now.strftime(APACHE_TIME_FORMAT)))

            if "POST" in data['method'] and data['token_id'] == "-":
                access_key = parse_access_key(data['url'])
                if access_key is not None:
                    data['token_id'] = HWExtend.b64encodeAK(access_key)

            data['url'] = encode_url(data['url'])

            if "GET" in data['method']:
                log.info(DRM_LOG_FORMAT % data, extra={"type": "operate"})
            else:
                # add log for CTS
                data['opt_time'] = int(round(time.time() * 1000))
                # get the user info
                try:
                    keystone_ca = "/etc/keystone/ssl/certs/ca.pem"
                    keystone_signing_cert = \
                        "/etc/keystone/ssl/certs/signing_cert.pem"
                    token_orig = request.headers['X-Auth-Token'].strip()
                    token_orig2 = cms.token_to_cms(token_orig)
                    token_decrypted = cms.cms_verify(
                        token_orig2,
                        keystone_signing_cert,
                        keystone_ca,
                        inform=cms.PKI_ASN1_FORM).decode('utf-8')
                    token_body = jsonutils.loads(token_decrypted)
                except Exception as ex:
                    log.info(('token_info get failed %(ex)s'), {'ex': ex})
                    token_body = None

                resource_map = {
                    'POST': {
                        3: [['api_version', 'tenant_id', 'resource_type']],
                        8: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id',
                             'resource_type1', 'resource_id1',
                             'action']],
                        6: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id', 'action']],
                        4: [['api_version', 'tenant_id', 'resource_type',
                             'action']]
                    },
                    'DELETE': {
                        4: [['api_version', 'tenant_id', 'resource_type',
                             'resource_id']],
                        7: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id',
                             'resource_type1', 'resource_id1']],
                        5: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id']],
                        6: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id',
                             'action']]
                    },
                    'PUT': {
                        4: [['api_version', 'tenant_id', 'resource_type',
                             'resource_id']],
                        6: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id',
                             'action']],
                        5: [['api_version', 'tenant_id', 'resource_type',
                             'resource_name', 'resource_id']]
                    }
                }

                resource_trace_map = {
                    'POST': {
                        3: [('create_%(resource_type)s')],
                        8: [('create_%(resource_type)s_%(resource_type1)s'
                             '_%(action)s')],
                        6: [('create_%(resource_type)s_%(action)s')],
                        4: [('create_%(resource_type)s_%(action)s')]
                    },
                    'DELETE': {
                        4: [('delete_%(resource_type)s')],
                        7: [('delete_%(resource_type)s_'
                             '%(resource_type1)s')],
                        5: [('delete_%(resource_type)s')],
                        6: [('delete_%(resource_type)s_%(action)s')]
                    },
                    'PUT': {
                        4: [('update_%(resource_type)s')],
                        6: [('update_%(resource_type)s_%(action)s')],
                        5: [('update_%(resource_type)s')]
                    }
                }

                # the location of different if resource_map has multi match
                resource_map_diff = {
                    'POST': {
                        3: [True, True, True],
                        8: [True, True, True, True, True, True, True, True],
                        6: [True, True, True, True, True, True],
                        4: [True, True, True, True]
                    },
                    'DELETE': {
                        4: [True, True, True, True],
                        7: [True, True, True, True, True, True, True],
                        5: [True, True, True, True, True],
                        6: [True, True, True, True, True, True]
                    },
                    'PUT': {
                        4: [True, True, True, True],
                        6: [True, True, True, True, True, True],
                        5: [True, True, True, True, True]
                    }
                }

                try:
                    if data['method'] in ['DELETE', 'PUT', 'POST']:
                        path_item = urlparse.urlparse(data['url']). \
                            path.lstrip('/').split('/')
                        resource_info, trace_info = \
                            get_info_from_resource(path_item,
                                                   resource_map[
                                                       data['method']],
                                                   resource_trace_map[
                                                       data['method']],
                                                   resource_map_diff[
                                                       data['method']])
                        data['opt_resourectype'] = get_dict_key(
                            resource_info,
                            'resource_type',
                            '-')
                        data['opt_resourcename'] = get_dict_key(
                            resource_info,
                            'resource_name',
                            '-')
                        data['opt_tracename'] = get_dict_key(
                            trace_info,
                            'trace_name',
                            '-')
                        data['opt_api_version'] = get_dict_key(resource_info,
                                                               'api_version',
                                                               '-')

                        if 400 < int(data['status']):
                            data['opt_trace_rating'] = 'warning'
                        else:
                            data['opt_trace_rating'] = 'normal'

                        data['opt_trace_type'] = get_dict_key(
                            request.headers, 'X-Request-Source-Type',
                            '-')
                        data['opt_source_ip'] = get_dict_key(
                            request.headers,
                            'X-Forwarded-For',
                            '-')

                        if "POST" in data['method']:
                            data['opt_resourceid'] = get_post_resource_id(
                                json.loads(response.body),
                                get_dict_key(
                                    resource_info,
                                    'resource_id',
                                    '-'))
                        else:
                            data['opt_resourceid'] = get_dict_key(
                                resource_info, 'resource_id', '-')
                except Exception as ex:
                    log.info(('resource_info get failed %(ex)s'),
                             {'ex': ex})

                try:
                    if token_body is not None:
                        if 'token' in token_body.keys():
                            data['opt_domainname'] = get_info_noexcept(
                                token_body['token'], 'user', 'domain',
                                'name') or '-'
                        else:
                            data['opt_domainname'] = '-'

                        if data['opt_domainname'] != '-':
                            data['opt_domainid'] = get_info_noexcept(
                                token_body['token'], 'user',
                                'domain', 'id') or '-'
                            data['opt_project_id'] = get_info_noexcept(
                                token_body['token'], 'project', 'id') or '-'
                            data['opt_username'] = get_info_noexcept(
                                token_body['token'], 'user', 'name') or '-'
                            data['opt_userid'] = get_info_noexcept(
                                token_body['token'], 'user', 'id') or '-'
                        else:
                            data['opt_domainname'] = 'Default'
                            data['opt_project_id'] = get_info_noexcept(
                                token_body['access']['token'],
                                'tenant', 'id') or '-'
                            data['opt_username'] = get_info_noexcept(
                                token_body['access'],
                                'user', 'name') or '-'
                            data['opt_userid'] = get_info_noexcept(
                                token_body['access'],
                                'user', 'id') or '-'
                    data['opt_service_type'] = 'ORCHESTRATION'
                except Exception as ex:
                    log.info(('other_info get failed %(ex)s'), {'ex': ex})

                log.info(CTS_LOG_FORMAT % data, extra={"type": "operate"})
        return response

    @classmethod
    def factory(cls, global_config, **local_config):
        """Used for paste app factories in paste.deploy config files.

        Any local configuration (that is, values under the [filter:APPNAME]
        section of the paste config) will be passed into the `__init__` method
        as kwargs.

        A hypothetical configuration would look like:

            [filter:analytics]
            redis_host = 127.0.0.1
            paste.filter_factory = nova.api.analytics:Analytics.factory

        which would result in a call to the `Analytics` class as

            import nova.api.analytics
            analytics.Analytics(app_from_paste, redis_host='127.0.0.1')

        You could of course re-implement the `factory` method in subclasses,
        but using the kwarg passing it shouldn't be necessary.

        """

        def _factory(app):
            return cls(app, **local_config)

        return _factory
