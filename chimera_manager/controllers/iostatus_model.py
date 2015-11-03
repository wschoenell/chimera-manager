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
    key = Column(String, default=None) # this is a self generated key to lock an instrument. Use it to unlock
    lastUpdate = Column(DateTime, default=None)
    lastChange = Column(DateTime, default=None)

metaData.create_all(engine)
