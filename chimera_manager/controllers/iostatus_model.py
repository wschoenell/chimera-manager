from chimera_manager.core.constants import DEFAULT_STATUS_DATABASE

from sqlalchemy import (Column, String, Integer, DateTime, Boolean, ForeignKey,
                        Float, PickleType, MetaData, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation, backref

engine = create_engine('sqlite:///%s' % DEFAULT_STATUS_DATABASE, echo=False)

metaData = MetaData()
metaData.bind = engine

Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metaData)

class InstrumentOperationStatus(Base):
    __tablename__ = "iostatus"
    id = Column(Integer, primary_key=True)
    instrument = Column(String, default=None)
    status = Column(Integer, default=None)
    # key = Column(String, default=None) # this is a self generated key to lock an instrument. Use it to unlock
    keylist = relation("KeyList", backref=backref("iostatus", order_by="KeyList.key_id"),
                         cascade="all, delete, delete-orphan")    # list of keys that locks the instrument.
    lastUpdate = Column(DateTime, default=None)
    lastChange = Column(DateTime, default=None)

class KeyList(Base):

    id         = Column(Integer, primary_key=True)
    key_id = Column(Integer, ForeignKey("iostatus.id"))

    key = Column(String, default=None)
    updatetime = Column(DateTime, default=None)
    active = Column(Boolean, default=True)

    __tablename__ = "keylist"
    # __mapper_args__ = {'polymorphic_on': check_type}

metaData.create_all(engine)
