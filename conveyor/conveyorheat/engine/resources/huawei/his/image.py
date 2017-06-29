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

from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine import resource
from conveyor.conveyorheat.engine import support
from conveyor.i18n import _


class HISImage(resource.Resource):
    """A resource managing hyper images in HIS.

    A resource provides managing images that are meant to be used with other
    services.
    """

    support_status = support.SupportStatus(version='2014.2')

    PROPERTIES = (
        NAME, ORIGINAL_IMAGE_ID
    ) = (
        'name', 'original_image_id'
    )

    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('Name for the hyper container image.'),
            required=True
        ),
        ORIGINAL_IMAGE_ID: properties.Schema(
            properties.Schema.STRING,
            _('The image ID.'),
            required=True
        ),
    }

    # default_client_name = 'his'

    entity = 'images'

    def handle_create(self):
        args = dict((k, v) for k, v in self.properties.items()
                    if v is not None)
        hyper_image_id = \
            self.his().images.convert(**args)['hyper_image_id']
        self.resource_id_set(hyper_image_id)
        return hyper_image_id

    def check_create_complete(self, image_id):
        image = self.glance().images.get(image_id)
        if image is not None:
            return image.status == 'active'
        return False

    def _show_resource(self):
        image = self.glance().images.get(self.resource_id)
        return dict(image)

    def validate(self):
        super(HISImage, self).validate()


def resource_mapping():
    return {
        'Huawei::FusionSphere::HIS': HISImage
    }
