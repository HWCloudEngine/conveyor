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

import copy
import retrying

from conveyor.conveyorheat.common import exception
from conveyor.conveyorheat.engine import constraints
from conveyor.conveyorheat.engine import properties
from conveyor.conveyorheat.engine.resources.huawei.elb import elb_res_base
from conveyor.conveyorheat.engine.resources.huawei.elb import utils
from conveyor.i18n import _
from conveyor.i18n import _LI

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class Member(elb_res_base.ElbBaseResource):
    """A resource for member .

    Member resource for Elastic Load Balance Service.
    """

    MEMBER_KEYS = (
        SERVER_ID, ADDRESS,
    ) = (
        'server_id', 'address',
    )
    PROPERTIES = (
        LISTENER_ID, MEMBERS,
    ) = (
        'listener_id', 'members',
    )

    properties_schema = {
        LISTENER_ID: properties.Schema(
            properties.Schema.STRING,
            _('The ID of listener associated.'),
            required=True,
            constraints=[
                constraints.CustomConstraint('elb.ls')
            ]
        ),
        MEMBERS: properties.Schema(
            properties.Schema.LIST,
            _('The servers to add as members.'),
            schema=properties.Schema(
                properties.Schema.MAP,
                schema={
                    SERVER_ID: properties.Schema(
                        properties.Schema.STRING,
                        _('ID of the server to add.'),
                        constraints=[
                            constraints.CustomConstraint('nova.server')
                        ],
                        required=True,
                    ),
                    ADDRESS: properties.Schema(
                        properties.Schema.STRING,
                        _('The private address of the server to add.'),
                        required=True,
                    )
                }
            ),
            required=True,
            constraints=[
                constraints.Length(min=1, max=6)
            ],
            update_allowed=True
        ),
    }

    def validate(self):
        super(Member, self).validate()
        members = self.properties[self.MEMBERS]
        server_ids = [m['server_id'] for m in members]
        if len(server_ids) != len(set(server_ids)):
            msg = (_('The %(sid)s must be different in property %(mem)s.') %
                   {'sid': self.SERVER_ID,
                    'mem': self.MEMBERS})
            raise exception.StackValidationFailed(message=msg)

    def _parse_members_entities(self, members_info):
        base_members_info = []
        member_ids = []
        for m in members_info:
            m_id = m['id']
            member_ids.append(m_id)
            base_info = None
            if m.get('server_id'):
                base_info = '.'.join([m_id, m.get('server_id')])
            else:
                base_info = m_id
            base_members_info.append(base_info)

        return member_ids, base_members_info

    def _handle_job_success(self, operate='create', entities=None):
        if entities:
            members_info = entities.get('members', [])
            mem_ids, base_info = self._parse_members_entities(
                members_info)
            if operate == 'create':
                if mem_ids:
                    # set 'mem_id1, mem_id2, mem_id3...' as resource_id
                    self.resource_id_set(','.join(mem_ids))
                if base_info:
                    # set resource_data to:
                    # {'members': 'mid1.sid1, mid2.sid2'}
                    self.data_set('members', ','.join(base_info))
                return
            old_member_ids = self.resource_id.split(',')
            old_base_info = self.data().get('members')
            old_base_list = old_base_info.split(',')

            if operate == 'update_add':
                member_ids = old_member_ids + mem_ids
                self.resource_id_set(','.join(set(member_ids)))
                self.data_set('members', ','.join(old_base_list + base_info))
            elif operate == 'update_remove':
                member_ids = set(old_member_ids) - set(mem_ids)
                self.resource_id_set(','.join(member_ids))
                ms_infos = copy.deepcopy(old_base_list)
                for info in base_info:
                    for m in old_base_list:
                        # there is no server_id in response.entities
                        # of remove_member, make sure member_id equal
                        if info.split('.')[0] == m.split('.')[0]:
                            ms_infos.remove(m)
                            break

                self.data_set('members', ','.join(ms_infos))

    def _get_vpc_tag(self):
        ls_id = self.properties[self.LISTENER_ID]
        lb_id = self.client().listener.get(ls_id).loadbalancer_id
        vpc_id = self.client().loadbalancer.get(lb_id).vpc_id

        return vpc_id

    @retrying.retry(stop_max_attempt_number=60,
                    wait_fixed=2000,
                    retry_on_result=utils.retry_if_result_is_false)
    def _match_servers_tag(self, tag, ids):
        servers = self.client('nova').servers.list(search_opts={'tag': tag})
        tagged = []
        for m in ids:
            for s in servers:
                if s.id == m:
                    tagged.append(m)
                    break
        return len(tagged) == len(ids)

    def _tag_check(self, tag, ids):
        try:
            if self._match_servers_tag(tag, ids):
                LOG.info(_LI('Check tags success!'))
        except retrying.RetryError:
            # just log the find server's tag failed
            LOG.info(_LI('Check tags failed!'))

    def handle_create(self):
        vpc_id = self._get_vpc_tag()
        ids = [m[self.SERVER_ID] for m in self.properties[self.MEMBERS]]
        self._tag_check(vpc_id, ids)

        props = self._prepare_properties(self.properties)
        job_id = self.client().listener.add_member(**props)['job_id']
        job_info = {'job_id': job_id, 'action': self.action}
        self._set_job(job_info)
        return job_id

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            new_members = prop_diff.get(self.MEMBERS)
            old_members = self.properties[self.MEMBERS]
            add_members = [m for m in new_members if m not in old_members]
            remove_members = [m for m in old_members if m not in new_members]
            remove_ids = []
            stored_base_info = copy.deepcopy(
                self.data().get('members')).split(',')

            for rm in remove_members:
                for info in stored_base_info:
                    ms = info.split('.')
                    if rm['server_id'] == ms[1]:
                        remove_ids.append({'id': ms[0]})
                        break

            add_job_id = None
            remove_job_id = None
            self.add_job_success = True
            self.remove_job_success = True
            if add_members:
                vpc_id = self._get_vpc_tag()
                ids = [m[self.SERVER_ID] for m in add_members]
                self._tag_check(vpc_id, ids)
                add_job_id = self.client().listener.add_member(
                    listener_id=self.properties[self.LISTENER_ID],
                    members=add_members)['job_id']
                self.add_job_success = False
            if remove_ids:
                remove_job_id = self.client().listener.remove_member(
                    listener_id=self.properties[self.LISTENER_ID],
                    removeMember=remove_ids)['job_id']
                self.remove_job_success = False
            return add_job_id, remove_job_id

        return None, None

    def handle_delete(self):
        ls_id = self.properties[self.LISTENER_ID]
        # if there is no ls_id, maybe the listener resource
        # of the backup stack has not been created yet, in
        # this case, we don't have to call remove_member
        # with invalid listener id
        if not ls_id:
            return

        if not self.resource_id:
            job_info = self._get_job()
            job_id = job_info.get('job_id')
            if not job_id:
                return

            try:
                job_status, entities, error_code = self._get_job_info(job_id)
            except Exception as e:
                if self.client_plugin().is_not_found(e):
                    LOG.info('job %s not found', job_id)
                    return
                raise e

            if job_status == utils.SUCCESS:
                members_info = entities.get('members', [])
                member_ids, base_info = self._parse_members_entities(
                    members_info)
                self.resource_id_set(','.join(set(member_ids)))
            return
        member_id_list = self.resource_id.split(',')
        remove_members = [{'id': m} for m in member_id_list]
        job_id = self.client().listener.remove_member(
            listener_id=ls_id,
            removeMember=remove_members)['job_id']

        return job_id

    def check_create_complete(self, job_id):
        job_status, entities, error_code = self._get_job_info(job_id)
        if job_status == utils.FAIL:
            self._set_job({})
            raise exception.ResourceUnknownStatus(
                result=(_('Job %(job)s failed: %(error_code)s, '
                          '%(entities)s')
                        % {'job': job_id,
                           'error_code': error_code,
                           'entities': entities}),
                resource_status='Unknown')
        if job_status == utils.SUCCESS:
            self._handle_job_success(entities=entities)
            self._set_job({})
            return True

    def check_update_complete(self, job_ids):
        add_job_id, remove_job_id = job_ids
        if not add_job_id and not remove_job_id:
            return True
        # check add job
        if add_job_id and not self.add_job_success:
            job_status, entities, error_code = self._get_job_info(add_job_id)
            if job_status == utils.FAIL:
                raise exception.ResourceUnknownStatus(
                    result=(_('Job %(job)s failed: %(error_code)s, '
                              '%(entities)s')
                            % {'job': add_job_id,
                               'error_code': error_code,
                               'entities': entities}),
                    resource_status='Unknown')
            if job_status == utils.SUCCESS:
                self.add_job_success = True
                self._handle_job_success(operate='update_add',
                                         entities=entities)
        if remove_job_id and not self.remove_job_success:
            job_status, entities, error_code =\
                self._get_job_info(remove_job_id)
            if job_status == utils.FAIL:
                raise exception.ResourceUnknownStatus(
                    result=(_('Job %(job)s failed: %(error_code)s, '
                              '%(entities)s')
                            % {'job': remove_job_id,
                               'error_code': error_code,
                               'entities': entities}),
                    resource_status='Unknown')
            if job_status == utils.SUCCESS:
                self.remove_job_success = True
                self._handle_job_success(operate='update_remove',
                                         entities=entities)

        return self.add_job_success and self.remove_job_success

    def check_delete_complete(self, job_id):
        if not job_id:
            return True
        return self._check_job_success(job_id, ignore_not_found=True)


def resource_mapping():
    return {
        'OSE::ELB::Member': Member,
    }
