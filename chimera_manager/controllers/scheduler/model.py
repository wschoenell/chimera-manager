from chimera_manager.core.constants import DEFAULT_ROBOBS_DATABASE

from sqlalchemy import (Column, String, Integer, DateTime, Boolean, ForeignKey,
                        Float, PickleType, MetaData, Text, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation, backref

from chimera.util.position import Position

import logging as log

engine = create_engine('sqlite:///%s' % DEFAULT_ROBOBS_DATABASE, echo=False)
# log.debug('-- engine created with sqlite:///%s' % DEFAULT_PROGRAM_DATABASE)
metaData = MetaData()
metaData.bind = engine

Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metaData)

import datetime as dt

class Targets(Base):
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="Program")
    type = Column(String, default="OBJECT")
    lastObservation = Column(DateTime, default=None)
    observed = Column(Boolean, default=False)
    scheduled = Column(Boolean, default=False)
    targetRa = Column(Float, default=0.0)
    targetDec = Column(Float, default=0.0)
    targetEpoch = Column(Float, default=2000.)
    targetMag = Column(Float, default=0.0)
    magFilter = Column(String, default=None)
    link = Column(String, default=None)

    def __str__(self):
        raDec = Position.fromRaDec(self.targetRa, self.targetDec, 'J2000')

        if self.observed:
            msg = "#[id: %5d] [name: %15s %s] [type: %s] #LastObverved@: %s"
            return msg % (self.id, self.name, raDec,
                          self.type, self.lastObservation)
        else:
            msg = "#[id: %5d] [name: %15s %s] [type: %s] #NeverObserved"
            return msg % (self.id, self.name, raDec,
                          self.type,)


class BlockPar(Base):
    __tablename__ = "blockpar"
    id = Column(Integer, primary_key=True)
    bid = Column(Integer)
    pid = Column(String, default='')

    maxairmass = Column(Float, default=2.5)
    minairmass = Column(Float, default=-1.0)
    maxmoonBright = Column(Float, default=100.)  # percent
    minmoonBright = Column(Float, default=0.)  # percent
    minmoonDist = Column(Float, default=-1.)  # in degrees
    maxseeing = Column(Float, default=2.0)  # seing
    cloudcover = Column(Integer, default=0)  # must be defined by user
    schedalgorith = Column(Integer, default=0)  # scheduling algorith
    applyextcorr = Column(Boolean, default=False)

    def __str__(self):
        msg = "#[id: %4i][bid: %4i][PID: %10s][airmass: %5.2f][seeing: %5.2f][cloud: %2i][schedAlgorith: %2i]"
        return msg % (self.id, self.bid, self.pid, self.maxairmass, self.maxseeing,
                      self.cloudcover, self.schedalgorith)


class ObsBlock(Base):
    __tablename__ = "obsblock"
    id = Column(Integer, primary_key=True)
    objid = Column(Integer, ForeignKey("targets.id"))
    blockid = Column(Integer)
    bparid = Column(Integer, ForeignKey("blockpar.bid"))
    pid = Column(String, ForeignKey("projects.pid"))
    observed = Column(Boolean, default=False)
    scheduled = Column(Boolean, default=False)

    def __str__(self):
        return "#%i %s[%i] [observed: %i | scheduled: %i]" % (self.blockid, self.pid,
                                                              self.objid,
                                                              self.observed,
                                                              self.scheduled)


class BlockConfig(Base):
    __tablename__ = "blockconfig"
    id = Column(Integer, primary_key=True)
    bid = Column(Integer, ForeignKey("obsblock.blockid"))
    pid = Column(String, ForeignKey("projects.pid"))
    filter = Column(String, default=None)
    exptime = Column(Float, default=1.0)
    imagetype = Column(String, default=None)
    nexp = Column(Integer, default=1)

    def __str__(self):
        return "#%i %s[%i] [filter: %s | exptime: %f | nexp: %i]" % (self.id,
                                                                     self.pid,
                                                                     self.bid,
                                                                     self.filter,
                                                                     self.exptime,
                                                                     self.nexp)


class Projects(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    pid = Column(String, default="PID")
    pi = Column(String, default="Anonymous Investigator")
    abstract = Column(Text, default="")
    url = Column(String, default="")
    priority = Column(Integer, default=0)

    def __str__(self):
        return "#%3d %s pi:%s #abstract: %s #url: %s" % (self.id, self.flag,
                                                         self.pi,
                                                         self.abstract,
                                                         self.url)


class Program(Base):
    __tablename__ = "program"
    print "model.py"

    id = Column(Integer, primary_key=True)
    tid = Column(Integer, ForeignKey('targets.id'))
    name = Column(String, ForeignKey("targets.name"))
    pi = Column(String, default="Anonymous Investigator")

    priority = Column(Integer, default=0)

    createdAt = Column(DateTime, default=dt.datetime.today())
    finished = Column(Boolean, default=False)
    slewAt = Column(Float, default=0.0)
    exposeAt = Column(Float, default=0.0)

    # Extra information not present in standard chimera database schema,
    # required to link observing program with observing block
    pid = Column(String, ForeignKey("projects.pid"))  # Project ID
    blockid = Column(Integer, ForeignKey("blockpar.bid"))  # Block ID

    # actions = relation("Action", backref=backref("program", order_by="Action.id"),
    #                    cascade="all, delete, delete-orphan")

    def __str__(self):
        return "#%d %s pi:%s" % (self.id, self.name, self.pi)


class ObservingLog(Base):
    __tablename__ = "observinglog"

    id = Column(Integer, primary_key=True)
    time = Column(DateTime, default=dt.datetime.today())
    tid = Column(Integer, ForeignKey('targets.id'))
    name = Column(String, ForeignKey("targets.name"))
    priority = Column(Integer, ForeignKey("program.priority"),default=-1)
    action = Column(String)

    def __str__(self):
        return '%s [%s] P%s Action: %s' % ( self.time,
                                              self.name,
                                              self.priority,
                                              self.action)

###

#metaData.drop_all(engine)
metaData.create_all(engine)

