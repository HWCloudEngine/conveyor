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

from conveyor.conveyorheat.common import environment_format
from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine import function
from conveyor.conveyorheat.engine.resources.aws.autoscaling import \
    autoscaling_group as scaling
from conveyor.conveyorheat.engine import rsrc_defn

(SCALED_RESOURCE_TYPE,) = ('OS::Heat::ScaledResource',)


class AutoScalingGroup(scaling.AutoScalingGroup):

    def _environment(self):
        """Return the environment for the nested stack."""
        return {
            environment_format.PARAMETERS: {},
            environment_format.RESOURCE_REGISTRY: {
                SCALED_RESOURCE_TYPE: 'Huawei::FusionSphere::Instance',
            },
        }

    def validate(self):
        res = super(AutoScalingGroup, self).validate()
        if res:
            return res

        if self.properties.get(self.AVAILABILITY_ZONES) and \
                len(self.properties.get(self.AVAILABILITY_ZONES)) > 1:
            raise exception.NotSupported(feature=_("Anything other than one"
                                         "AvailabilityZone"))

    def _get_instance_definition(self):
        conf_refid = self.properties[self.LAUNCH_CONFIGURATION_NAME]
        conf = self.stack.resource_by_refid(conf_refid)

        props = function.resolve(conf.properties.data)
        props['Tags'] = self._tags()
        vpc_zone_ids = self.properties.get(AutoScalingGroup.VPCZONE_IDENTIFIER)
        if vpc_zone_ids:
            props['SubnetId'] = vpc_zone_ids[0]

        azs = self.properties.get(self.AVAILABILITY_ZONES)
        if azs:
            props['AvailabilityZone'] = azs[0]

        return rsrc_defn.ResourceDefinition(None,
                                            SCALED_RESOURCE_TYPE,
                                            props,
                                            conf.t.metadata())


def resource_mapping():
    return {
        'Huawei::FusionSphere::AutoScalingGroup': AutoScalingGroup,
    }
