from chimera.core.constants import DEFAULT_PROGRAM_DATABASE

from sqlalchemy import (Column, String, Integer, DateTime, Boolean, ForeignKey,
                        Float, PickleType, MetaData, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation, backref

engine = create_engine('sqlite:///%s' % DEFAULT_PROGRAM_DATABASE, echo=False)
metaData = MetaData()
metaData.bind = engine

Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metaData)

class List(Base):
    __tablename__ = "list"
    id         = Column(Integer, primary_key=True)
    status     = Column(Boolean, default=False) # check status.FlagStatus
    lastUpdate = Column(DateTime, default=None)
    name       = Column(String,default=None)

    eager      = Column(Boolean, default=False) # Run response every time. Normal operation is run
                                                # only when status change

    # check_id     = Column(Integer)
    # response_id     = Column(Integer)

    check      = relation("Check", backref=backref("list", order_by="Check.list_id"),
                         cascade="all, delete, delete-orphan")
    response   = relation("Response", backref=backref("list", order_by="Response.list_id"),
                         cascade="all, delete, delete-orphan")

    def __str__ (self):
        return "Item[%s]:%s Status[%i] LasUpdate: %s"%(self.name,'Eager' if self.eager else 'Normal',self.status,
                                                       self.lastUpdate)

class Check(Base):

    id         = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("list.id"))

    check_type = Column('type', String(100))


    __tablename__ = "check"
    __mapper_args__ = {'polymorphic_on': check_type}

class CheckTime(Check):
    __tablename__ = "checktime"
    __mapper_args__ = {'polymorphic_identity': 'CheckTime'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    sun_altitude = Column(Float, default=0.0) # The desired altitude
    above = Column(Boolean, default=True) # Is it above (True) or below (False) specified altitude?
    rising = Column(Boolean, default=False) # Is it rising (True) or setting (False)?

    def __init__(self, sun_alt,above,rising):
        self.sun_altitude = float(sun_alt)
        self.above = above.upper().replace(" ","") == "ABOVE"
        self.rising = rising.upper().replace(" ","") == 'RISING'

    def __str__ (self):
        return "checktime: Sun %s %.2f Degrees, %s" % ("above" if self.above else "below",
                                                       self.sun_altitude,
                                                       "rising" if self.rising else "setting")

class Response(Base):
    __tablename__ = "response"

    id         = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("list.id"))

    response_type = Column(String(100))

    # __mapper_args__ = {'polymorphic_on': response_type}

metaData.create_all(engine)
