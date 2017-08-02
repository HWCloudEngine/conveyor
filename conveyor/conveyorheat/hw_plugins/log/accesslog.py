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

import six
import sys
import urllib
import urlparse

from oslo_utils import uuidutils

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
