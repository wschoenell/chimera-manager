from chimera_manager.core.constants import DEFAULT_PROGRAM_DATABASE

from sqlalchemy import (Column, String, Integer, DateTime, Boolean, ForeignKey, Time, Interval,
                        Float, PickleType, MetaData, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation, backref

import datetime

engine = create_engine('sqlite:///%s' % DEFAULT_PROGRAM_DATABASE, echo=False)

metaData = MetaData()
metaData.bind = engine

Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metaData)

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

class CheckDome(Check):
    __tablename__ = "checkdome"
    __mapper_args__ = {'polymorphic_identity': 'CheckDome'}
    id = Column(Integer, ForeignKey('check.id'), primary_key=True)

    mode = Column(Integer,default=0)   # Operation mode

    def __init__(self, mode=0):
        self.mode= int(mode)

    def __str__(self):
        return "CheckDome: mode %i" % self.mode

class CheckTelescope(Check):
    __tablename__ = "checktelescope"
    __mapper_args__ = {'polymorphic_identity': 'CheckTelescope'}
    id = Column(Integer, ForeignKey('check.id'), primary_key=True)

    mode = Column(Integer,default=0)   # Operation mode

    def __init__(self, mode=0):
        self.mode= int(mode)

    def __str__(self):
        return "CheckTelescope: mode %i" % self.mode

class CheckTime(Check):
    __tablename__ = "checktime"
    __mapper_args__ = {'polymorphic_identity': 'CheckTime'}

    id = Column(Integer, ForeignKey('check.id'), primary_key=True)

    mode = Column(Integer,default=0)   # Operation mode

    time = Column(Time, default=None)  # Reference time
    deltaTime = Column(Interval,default=datetime.timedelta(0)) # offset to apply to reference time


    def __init__(self, mode=0,deltaTime=datetime.timedelta(0),time=None):
        self.mode= int(mode)
        self.time = time
        self.deltaTime = deltaTime if isinstance(deltaTime, datetime.timedelta) else \
            datetime.timedelta(hours=float(deltaTime))

    def __setattr__(self, key, value):
        if (key == 'deltaTime' or key == 'time') and value is not None:
            object.__setattr__(self,key,
                               value if isinstance(value, datetime.timedelta) else \
                                datetime.timedelta(hours=float(value)))
        elif value is not None:
            object.__setattr__(self,key,value)

    def __str__ (self):
        return "checktime: Mode %i (time: %s / deltaTime: %s)"% (self.mode,
                                                                 self.time,
                                                                 self.deltaTime)

class CheckHumidity(Check):
    __tablename__ = "checkhumidity"
    __mapper_args__ = {'polymorphic_identity': 'CheckHumidity'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    humidity = Column(Float, default=0.0)  # The desired humidity
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, humidity=0.,deltaTime=0.,mode=0):
        self.humidity= float(humidity)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checkhumidity: threshold %.2f " % (self.humidity)

class CheckTemperature(Check):
    __tablename__ = "checktemperature"
    __mapper_args__ = {'polymorphic_identity': 'CheckTemperature'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    temperature = Column(Float, default=0.0) # The desired temperature in Celsius
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, temperature=0.,deltaTime=0.,mode=0):
        self.temperature= float(temperature)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checktemperature: threshold %.2f " % (self.temperature)

class CheckWindSpeed(Check):
    __tablename__ = "checkwindspeed"
    __mapper_args__ = {'polymorphic_identity': 'CheckWindSpeed'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    windspeed = Column(Float, default=0.0) # The desired wind speed in m/s
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, windspeed=0.,deltaTime=0.,mode=0):
        self.windspeed= float(windspeed)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checkwindspeed: threshold %.2f " % (self.windspeed)

class CheckDewPoint(Check):
    __tablename__ = "checkdewpoint"
    __mapper_args__ = {'polymorphic_identity': 'CheckDewPoint'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    dewpoint = Column(Float, default=0.0) # The desired dewpoint in Celsius
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, dewpoint=0.,deltaTime=0.,mode=0):
        self.dewpoint= float(dewpoint)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checkdewpoint: threshold %.2f " % (self.dewpoint)

class CheckDew(Check):
    __tablename__ = "checkdew"
    __mapper_args__ = {'polymorphic_identity': 'CheckDew'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    tempdiff = Column(Float, default=0.0) # The desired difference in temperature and dew point
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, tempdiff=0.,deltaTime=0.,mode=0):
        self.tempdiff= float(tempdiff)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checkdew: threshold %.2f " % (self.tempdiff)

class CheckTransparency(Check):
    __tablename__ = "checktransparency"
    __mapper_args__ = {'polymorphic_identity': 'CheckTransparency'}

    id     = Column(Integer, ForeignKey('check.id'), primary_key=True)
    transparency = Column(Float, default=0.0) # The desired difference in temperature and dew point
    deltaTime = Column(Float, default=0.0)  # The desired time interval
    time = Column(DateTime, default=None) # A reference time
    mode = Column(Integer,default=0)  # Select the mode of operation:
    # 0 - True if humidity is higher than specified
    # 1 - True if humidity is lower than specified and time is larger than the desired interval

    def __init__(self, transparency=0.,deltaTime=0.,mode=0):
        self.transparency= float(transparency)
        self.deltaTime= deltaTime
        self.mode= mode

    def __str__ (self):
        return "checktransparency: threshold %.2f " % (self.transparency)

class AskListener(Check):
    __tablename__ = "asklistener"
    __mapper_args__ = {'polymorphic_identity': 'AskListener'}

    id       = Column(Integer, ForeignKey('check.id'), primary_key=True)
    question = Column(String)
    waittime = Column(Integer)

    # response   = relation("Response", backref=backref("question", order_by="Response.list_id"),
    #                      cascade="all, delete, delete-orphan")
    def __init__(self, question='', waittime=10):
        self.question = question
        self.waittime = waittime

    def __str__(self):
        return "[waittime: %i] %s" % (self.waittime,self.question)

class CheckInstrumentFlag(Check):
    __tablename__ = "checkinstrumentflag"
    __mapper_args__ = {'polymorphic_identity': 'CheckInstrumentFlag'}

    id       = Column(Integer, ForeignKey('check.id'), primary_key=True)
    instrument = Column(String)
    flag = Column(String)
    mode = Column(Integer)

    # response   = relation("Response", backref=backref("question", order_by="Response.list_id"),
    #                      cascade="all, delete, delete-orphan")
    def __init__(self, instrument='', flag='', mode=0):
        self.instrument = instrument
        self.flag = flag
        self.mode = mode

    def __str__(self):
        return "[CheckInstrumentFlag] %s.%s" % (self.instrument,self.flag)

class Response(Base):
    __tablename__ = "response"

    id         = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("list.id"))
    response_id = Column(String)

    response_type = Column(String(100))
    __mapper_args__ = {'polymorphic_on': response_type}

    def __str__(self):
        return "%s"%self.response_type

    # __mapper_args__ = {'polymorphic_on': response_type}

class BaseResponse(Response):
    __tablename__ = "baseresponse"
    __mapper_args__ = {'polymorphic_identity': 'BaseResponse'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)

    def __init__(self, response_id):
        self.response_id = response_id

    def __str__(self):
        return "%s"%self.response_id

class LockInstrument(Response):
    __tablename__ = 'lockinstrument'
    __mapper_args__ = {'polymorphic_identity': 'LockInstrument'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    instrument = Column(String)
    key = Column(String)

    def __init__(self, instrument='', key=''):
        self.response_id = self.__tablename__.upper()
        self.instrument = instrument
        self.key = key

    def __str__(self):
        return "Lock: instrument(%s) key(%s)" % (self.instrument,
                                                 self.key)

class UnlockInstrument(Response):
    __tablename__ = 'unlockinstrument'
    __mapper_args__ = {'polymorphic_identity': 'UnlockInstrument'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    instrument = Column(String)
    key = Column(String)

    def __init__(self, instrument='', key=''):
        self.response_id = self.__tablename__.upper()
        self.instrument = instrument
        self.key = key

    def __str__(self):
        return "Unlock: instrument(%s) key(%s)" % (self.instrument,
                                                   self.key)

class SetInstrumentFlag(Response):
    __tablename__ = "setinstrumentflag"
    __mapper_args__ = {'polymorphic_identity': 'SetInstrumentFlag'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    instrument = Column(String)
    flag = Column(Integer)

    def __init__(self,instrument='',flag=''):
        self.response_id = self.__tablename__.upper()
        self.instrument = instrument
        self.flag = int(flag)

    def __str__(self):
        return "SetFlag: instrument(%s) flag(%s)"%(self.instrument,
                                                   self.flag)

class Question(Response):
    __tablename__ = "question"
    __mapper_args__ = {'polymorphic_identity': 'Question'}

    id       = Column(Integer, ForeignKey('response.id'), primary_key=True)
    question = Column(String)
    waittime = Column(Integer)

    # response   = relation("Response", backref=backref("question", order_by="Response.list_id"),
    #                      cascade="all, delete, delete-orphan")

    def __init__(self):
        self.response_id = self.__tablename__.upper()

    def __str__(self):
        return "[waittime: %i] %s" % (self.waittime,self.question)

class SendTelegram(Response):
    __tablename__ = "sendtelegram"
    __mapper_args__ = {'polymorphic_identity': 'SendTelegram'}

    id       = Column(Integer, ForeignKey('response.id'), primary_key=True)
    message = Column(String)

    def __init__(self,message=''):
        self.response_id = self.__tablename__.upper()
        self.message = message

    def __str__(self):
        return "[SendTelegram]: %s" % (self.message)

class DomeFan(Response):
    __tablename__ = "domefan"
    __mapper_args__ = {'polymorphic_identity': 'DomeFan'}

    id       = Column(Integer, ForeignKey('response.id'), primary_key=True)
    fan = Column(String)
    mode = Column(Integer)
    speed = Column(Float)
    direction = Column(String)

    def __init__(self,fan='/Fan/0',mode=0,speed=0.,direction='FORWARD'):
        self.response_id = self.__tablename__.upper()
        self.fan = fan
        self.mode = mode
        self.speed = speed
        self.direction = direction

    def __str__(self):
        return "[DomeFan]: %s" % (self.fan)

class ActivateItem(Response):
    __tablename__ = "activateitem"
    __mapper_args__ = {'polymorphic_identity': 'ActivateItem'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    item = Column(String)

    def __init__(self,item=''):
        self.response_id = self.__tablename__.upper()
        self.item = item.upper()

    def __str__(self):
        return "Activate: %s"%(self.item)

class DeactivateItem(Response):
    __tablename__ = "deactivateitem"
    __mapper_args__ = {'polymorphic_identity': 'DeactivateItem'}

    id     = Column(Integer, ForeignKey('response.id'), primary_key=True)
    item = Column(String)

    def __init__(self,item=''):
        self.response_id = self.__tablename__.upper()
        self.item = item.upper()

    def __str__(self):
        return "Deactivate: %s"%(self.item)

metaData.create_all(engine)
