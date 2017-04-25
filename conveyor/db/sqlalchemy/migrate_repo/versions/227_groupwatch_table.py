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
import uuid

import sqlalchemy

from conveyor.db.sqlalchemy.types import Json


def upgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine

    _build_gw_tables(meta)


def _build_gw_tables(meta):

    alarm = sqlalchemy.Table(
        'gw_alarm', meta,
        sqlalchemy.Column('id', sqlalchemy.String(36),
                          primary_key=True, nullable=False,
                          default=lambda: str(uuid.uuid4())),
        sqlalchemy.Column('resource_id', sqlalchemy.String(36)),
        sqlalchemy.Column('created_at', sqlalchemy.DateTime),
        sqlalchemy.Column('updated_at', sqlalchemy.DateTime),
        sqlalchemy.Column('group_id', sqlalchemy.String(36),
                          index=True, nullable=True),
        sqlalchemy.Column('meter_name', sqlalchemy.String(255),
                          nullable=False),
        sqlalchemy.Column('data', Json),
        sqlalchemy.Column('actions', Json),
        sqlalchemy.Column('tenant', sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column('user', sqlalchemy.String(64), nullable=False),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    group = sqlalchemy.Table(
        'gw_group', meta,
        sqlalchemy.Column('id', sqlalchemy.String(36),
                          primary_key=True, nullable=False,
                          default=lambda: str(uuid.uuid4())),
        sqlalchemy.Column('created_at', sqlalchemy.DateTime),
        sqlalchemy.Column('updated_at', sqlalchemy.DateTime),
        sqlalchemy.Column('name', sqlalchemy.String(255), nullable=False),
        sqlalchemy.Column('type', sqlalchemy.String(255), nullable=True),
        sqlalchemy.Column('data', Json),
        sqlalchemy.Column('tenant', sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column('user', sqlalchemy.String(64), nullable=False),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    member = sqlalchemy.Table(
        'gw_member', meta,
        sqlalchemy.Column('id', sqlalchemy.String(36),
                          primary_key=True, nullable=False,
                          default=lambda: str(uuid.uuid4())),
        sqlalchemy.Column('name', sqlalchemy.String(255), nullable=True),
        sqlalchemy.Column('created_at', sqlalchemy.DateTime),
        sqlalchemy.Column('updated_at', sqlalchemy.DateTime),
        sqlalchemy.Column('group_id', sqlalchemy.String(36),
                          sqlalchemy.ForeignKey('gw_group.id'),
                          nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    tables = (
        group,
        alarm,
        member,
    )

    for index, table in enumerate(tables):
        try:
            table.create(checkfirst=True)
        except Exception:
            # If an error occurs, just raise the exception
            raise
