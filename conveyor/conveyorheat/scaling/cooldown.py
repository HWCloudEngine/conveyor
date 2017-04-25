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

from oslo_config import cfg
from oslo_utils import timeutils
import six


class CooldownMixin(object):
    """Utility class to encapsulate Cooldown related logic.

    This class is shared between AutoScalingGroup and ScalingPolicy.
    This logic includes both cooldown timestamp comparing and scaling in
    progress checking.
    """
    def _timeout(self):
        last_adjust_time = self.data().get('last_adjust_time')
        if not last_adjust_time:
            return False

        timeout_seconds = (self.stack.timeout_mins * 60
                           if self.stack.timeout_mins
                           else cfg.CONF.stack_action_timeout)

        try:
            if timeutils.is_older_than(last_adjust_time, timeout_seconds):
                return True
        except ValueError:
            pass

        return False

    def _is_scaling_allowed(self):
        metadata = self.metadata_get()
        # When scaling is in progress, heat-engine process restart,
        # 'scaling_in_progress' will be always True, scaling will can not be
        # triggered any more. So we need to recover this situation when scaling
        # is timeout.
        if metadata.get('scaling_in_progress') and not self._timeout():
            return False
        try:
            # Negative values don't make sense, so they are clamped to zero
            cooldown = max(0, self.properties[self.COOLDOWN])
        except TypeError:
            # If not specified, it will be None, same as cooldown == 0
            cooldown = 0

        if cooldown != 0:
            try:
                if 'cooldown' not in metadata:
                    # Note: this is for supporting old version cooldown logic
                    if metadata:
                        last_adjust = next(six.iterkeys(metadata))
                        if not timeutils.is_older_than(last_adjust, cooldown):
                            return False
                else:
                    last_adjust = next(six.iterkeys(metadata['cooldown']))
                    if not timeutils.is_older_than(last_adjust, cooldown):
                        return False
            except ValueError:
                # occurs when metadata has only {scaling_in_progress: False}
                pass

        # Assumes _finished_scaling is called
        # after the scaling operation completes
        metadata['scaling_in_progress'] = True
        self.metadata_set(metadata)

        # Set last_adjust_time because we need to check it before adjust if
        # 'scaling_in_progress' is True.
        self.data_set('last_adjust_time', timeutils.utcnow().isoformat())
        return True

    def _finished_scaling(self, cooldown_reason,
                          changed_size=True):
        # If we wanted to implement the AutoScaling API like AWS does,
        # we could maintain event history here, but since we only need
        # the latest event for cooldown, just store that for now
        metadata = self.metadata_get()
        if changed_size:
            now = timeutils.utcnow().isoformat()
            metadata['cooldown'] = {now: cooldown_reason}
        metadata['scaling_in_progress'] = False
        self.metadata_set(metadata)
