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

import base64
from keystoneclient.common import cms


# change PKI id to UUID
def pkiToUuid(token):
    return cms.cms_hash_token(token)


# encode token to a partial base64 string.
def b64encodeToken(token):
    return "encode-" + base64.encodestring(pkiToUuid(token))[:32]


# encode access key to a partial base64 string.
def b64encodeAK(accesskey):
    return "encode-" + base64.encodestring(accesskey)[:32]


def hasSensitiveStr(inStr):
    sensitiveStr = ['Password', 'PASSWORD', 'password', 'Pswd',
                    'PSWD', 'signature', 'HmacSHA256']
    for item in sensitiveStr:
        if item in str(inStr):
            return True

    return False
