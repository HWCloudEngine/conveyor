# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Piston Cloud Computing, Inc.
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
"""
SQLAlchemy models for conveyor data.
"""

from oslo.config import cfg
from oslo.db.sqlalchemy import models
from sqlalchemy import Column, Index, Integer, BigInteger, Enum, String, schema
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import orm
from sqlalchemy import ForeignKey, DateTime, Boolean, Text, Float

from conveyor.common import timeutils

BASE = declarative_base()


def MediumText():
    return Text().with_variant(MEDIUMTEXT(), 'mysql')


class ConveyorBase(models.SoftDeleteMixin,
               models.TimestampMixin,
               models.ModelBase):
    metadata = None

    # TODO(ekudryashova): remove this after both conveyor and oslo.db
    # will use oslo.utils library
    # NOTE: Both projects(conveyor and oslo.db) use `timeutils.utcnow`, which
    # returns specified time(if override_time is set). Time overriding is
    # only used by unit tests, but in a lot of places, temporarily overriding
    # this columns helps to avoid lots of calls of timeutils.set_override
    # from different places in unit tests.
    created_at = Column(DateTime, default=lambda: timeutils.utcnow())
    updated_at = Column(DateTime, onupdate=lambda: timeutils.utcnow())

    def save(self, session=None):
        from conveyor.db.sqlalchemy import api

        if session is None:
            session = api.get_session()

        super(ConveyorBase, self).save(session=session)


class Plan(BASE, ConveyorBase):
    """Represents a plan."""
    __tablename__ = "plans"
    __table_args__ = (
        Index('plan_id', 'plan_id', unique=True), 
    )

    id = Column(Integer, primary_key=True)
    expire_at = Column(DateTime)
    plan_id = Column(String(length=36), nullable=False)
    project_id = Column(String(length=36), nullable=False)
    user_id = Column(String(length=36), nullable=False)
    task_status = Column(String(length=255))
    plan_status = Column(String(length=255))
    plan_type = Column(String(length=255))
    original_resources = Column( String(length=1023))
    updated_resources   = Column(String(length=1023))
    stack_id =  Column(String(length=36))


