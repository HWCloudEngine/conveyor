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

"""
Main abstraction layer for retrieving and storing information about disk
images used by the compute layer.
"""

from hisclient.exc import Unauthorized
from hisclient.v2.client import Client as his_cli
from oslo_log import log as logging

from conveyor.conveyorheat.common import config
from conveyor.i18n import _LE

LOG = logging.getLogger(__name__)


def hisclient(token):
    endpoint = config.get_client_option('his', 'url')
    args = {
        'token': token,
        'insecure': config.get_client_option('his', 'insecure'),
        'timeout': config.get_client_option('his', 'timeout'),
        'cacert': config.get_client_option('his', 'ca_file'),
        'cert': config.get_client_option('his', 'cert_file'),
        'key': config.get_client_option('his', 'key_file'),
        'ssl_compression': False
    }
    return his_cli(endpoint=endpoint, **args)


class API(object):
    """Responsible for exposing a relatively stable internal API for other
    modules in his to retrieve information about hyper images.
    """

    def get_hyper_image(self, context, original_image_id):
        """Returns hyper image id.

        :param context: The `context.Context` object for the request
        :param original_image_id: the image uuid.
        """
        try:
            image = hisclient(context.auth_token). \
                images.image_show(original_image_id)
            if image and image.get('task') and \
                            image['task']['status'] == 'success':
                return image['task']['hyper_image_id']
            return None
        except Unauthorized as unauth:
            raise unauth
        except Exception as e:
            LOG.error(_LE("error in get_hyper_image"))
            raise e
