from chimera_manager.core.constants import DEFAULT_PROGRAM_DATABASE

from sqlalchemy import (Column, String, Integer, DateTime, Boolean, ForeignKey,
                        Float, PickleType, MetaData, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation, backref

engine = create_engine('sqlite:///%s' % DEFAULT_PROGRAM_DATABASE, echo=False)
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

class List(Base):
    __tablename__ = "list"
    id         = Column(Integer, primary_key=True)
    status     = Column(Integer, default=0) # The status flag id
    active     = Column(Boolean, default=True) # is item active (included in check routine)?
    lastUpdate = Column(DateTime, default=None)
    lastChange = Column(DateTime, default=None)
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

class CheckHumidity(Check):
    __tablename__ = "checkhumidity"
    __mapper_args__ = {'polymorphic_identity': 'CheckHumidity'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    humidity = Column(Float, default=0.0) # The desired humidity

    def __init__(self, humidity):
        self.humidity= float(humidity)

    def __str__ (self):
        return "checkhumidity: threshold %.2f " % (self.humidity)

class CheckTemperature(Check):
    __tablename__ = "checktemperature"
    __mapper_args__ = {'polymorphic_identity': 'CheckTemperature'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    temperature = Column(Float, default=0.0) # The desired temperature in Celsius

    def __init__(self, temperature):
        self.temperature= float(temperature)

    def __str__ (self):
        return "checktemperature: threshold %.2f " % (self.temperature)

class CheckWindSpeed(Check):
    __tablename__ = "checkwindspeed"
    __mapper_args__ = {'polymorphic_identity': 'CheckWindSpeed'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    windspeed = Column(Float, default=0.0) # The desired wind speed in m/s

    def __init__(self, windspeed):
        self.windspeed= float(windspeed)

    def __str__ (self):
        return "checkwindspeed: threshold %.2f " % (self.windspeed)

class CheckDewPoint(Check):
    __tablename__ = "checkdewpoint"
    __mapper_args__ = {'polymorphic_identity': 'CheckDewPoint'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    dewpoint = Column(Float, default=0.0) # The desired dewpoint in Celsius

    def __init__(self, dewpoint):
        self.dewpoint= float(dewpoint)

    def __str__ (self):
        return "checkdewpoint: threshold %.2f " % (self.dewpoint)

class CheckDew(Check):
    __tablename__ = "checkdew"
    __mapper_args__ = {'polymorphic_identity': 'CheckDew'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    tempdiff = Column(Float, default=0.0) # The desired difference in temperature and dew point

    def __init__(self, tempdiff):
        self.tempdiff= float(tempdiff)

    def __str__ (self):
        return "checkdew: threshold %.2f " % (self.tempdiff)

class Response(Base):
    __tablename__ = "response"

    id         = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("list.id"))

    response_type = Column(String(100))

    def __str__(self):
        return "%s"%self.response_type

    # __mapper_args__ = {'polymorphic_on': response_type}

class ResponseLock(Base):
    __tablename__ = "responselock"

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    instrument = Column(String)
    key = Column(String)

    def __str__(self):
        return "ResponseLock: instrument(%s) key(%s)"%(self.instrument,
                                                       self.key)
metaData.create_all(engine)
