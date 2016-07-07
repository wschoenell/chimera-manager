import os
import logging
import shutil
import time
import numpy as np

from chimera_manager.controllers.scheduler.model import Session as RSession
from chimera_manager.controllers.scheduler.model import (Program, Targets, BlockPar)

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.site import datetimeFromJD
from chimera.controllers.scheduler.states import State as SchedState
from chimera.controllers.scheduler.status import SchedulerStatus
from chimera.controllers.scheduler.model import Session
from chimera.util.position import Position
from chimera.util.enum import Enum
from chimera.util.output import blue, green, red

RobState = Enum('OFF', 'ON')

class RobObs(ChimeraObject):

    __config__ = {"site" : "/Site/0",
                  "schedulers" : "/Scheduler/0",
                  "weatherstations" : None,
                  "seeingmonitors"  : None,
                  "cloudsensors"    : None,
                  }

    def __init__(self):
        ChimeraObject.__init__(self)
        self.rob_state = RobState.OFF

    def __start__(self):

        self.log.debug("here")

        self._scheduler_list = self["schedulers"].split(',')

        self._connectSchedulerEvents()

        self._debuglog = logging.getLogger('_robobs_debug_')
        logfile = os.path.join(SYSTEM_CONFIG_DIRECTORY, "robobs_%s.log"%time.strftime("%Y%m%d-%H%M%S"))
        if os.path.exists(logfile):
            shutil.move(logfile, os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                              "robobs.log_%s"%time.strftime("%Y%m%d-%H%M%S")))

        _log_handler = logging.FileHandler(logfile)
        _log_handler.setFormatter(logging.Formatter(
            fmt='%(asctime)s[%(levelname)s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
        # _log_handler.setLevel(logging.DEBUG)
        self._debuglog.setLevel(logging.DEBUG)
        self._debuglog.addHandler(_log_handler)
        self.log.setLevel(logging.INFO)

    def __stop__(self):

        self._disconnectSchedulerEvents()

    def start(self):
        self._debuglog.debug("Switching robstate on...")
        self.rob_state = RobState.ON

        return True

    def stop(self):
        self._debuglog.debug("Switching robstate off...")
        self.rob_state = RobState.OFF

        return True

    def getSite(self):
        return self.getManager().getProxy(self["site"])

    def getSched(self,index=0):
        return self.getManager().getProxy(self._scheduler_list[index])

    def _connectSchedulerEvents(self):
        sched = self.getSched()
        if not sched:
            self.log.warning("Couldn't find scheduler.")
            return False

        sched.programBegin += self.getProxy()._watchProgramBegin
        sched.programComplete += self.getProxy()._watchProgramComplete
        sched.actionBegin += self.getProxy()._watchActionBegin
        sched.actionComplete += self.getProxy()._watchActionComplete
        sched.stateChanged += self.getProxy()._watchStateChanged

    def _disconnectSchedulerEvents(self):

        sched = self.getSched()
        if not sched:
            self.log.warning("Couldn't find scheduler.")
            return False

        sched.programBegin -= self.getProxy()._watchProgramBegin
        sched.programComplete -= self.getProxy()._watchProgramComplete
        sched.actionBegin -= self.getProxy()._watchActionBegin
        sched.actionComplete -= self.getProxy()._watchActionComplete
        sched.stateChanged -= self.getProxy()._watchStateChanged

    def _watchProgramBegin(self,program):
        session = Session()
        program = session.merge(program)
        self._debuglog.debug('Program %s started' % program)

    def _watchProgramComplete(self, program, status, message=None):
        session = Session()
        program = session.merge(program)
        self._debuglog.debug('Program %s completed with status %s(%s)' % (program,
                                                                    status,
                                                                    message))

    def _watchActionBegin(self,action, message):
        session = Session()
        action = session.merge(action)
        self._debuglog.debug("%s:%s %s ..." % (blue("[action] "), action,message), end="")


    def _watchActionComplete(self,action, status, message=None):
        session = Session()
        action = session.merge(action)

        if status == SchedulerStatus.OK:
            self._debuglog.debug("%s: %s" % (action,
                                            green(str(status))))
        else:
            self._debuglog.debug("%s: %s (%s)" % (action,
                                     red(str(status)), red(str(message))))

    def _watchStateChanged(self, newState, oldState):

        self._debuglog.debug("State changed %s -> %s..." % (oldState,
                                                            newState))

        if oldState == SchedState.IDLE and newState == SchedState.OFF:
            if self.rob_state == RobState.ON:
                self._debuglog.debug("Scheduler went from BUSY to OFF. Needs resheduling...")
                program = self.reshedule()
                if program is not None:
                    self._debuglog.debug("Adding program %s to sheduler and starting." % program)
                else:
                    self._debuglog.debug("No program on robobs queue.")
            else:
                self._debuglog.debug("Current state is off. Won't respond.")

    def reshedule(self):

        session = RSession()

        site = self.getSite()
        nowmjd = site.MJD()

        program = None

        # Get a list of priorities
        plist = self.getPList()

        if len(plist) == 0:
            return None

        # Get project with highest priority as reference
        priority = plist[0]
        program,plen = self.getProgram(nowmjd,plist[0])

        if program:
            program = session.merge(program)

        if program and ( (not program.slewAt) and (self.checkConditions(program,nowmjd))):
            # Program should be done right away!
            return program
        elif program:
            self._debuglog.warning('Current program length: %.2f m. Slew@: %.3f'%(plen/60.,program.slewAt))

        for p in plist[1:]:

            # Get program and program duration (lenght)

            aprogram,aplen = self.getProgram(nowmjd,p)

            aprogram = session.merge(aprogram)

            if not aprogram:
                continue

            if not program:
                program = aprogram

            if not self.checkConditions(aprogram,aprogram.slewAt):
                # if condition is False, project cannot be executed. Go to next in the list
                continue

            self._debuglog.warning('Current program length: %.2f m. Slew@: %.3f'%(aplen/60.,aprogram.slewAt))
            #return program
            #if aplen < 0 and program:
            #	log.debug('Using normal program (aplen < 0)...')
            #	return program

            # If alternate program fits will send it instead

            waittime=(program.slewAt-nowmjd)*86.4e3

            if waittime < 0:
                waittime = 0

            self._debuglog.warning('Wait time is: %.2f m'%(waittime/60.))

            if waittime>aplen or waittime > 2.*plen:
            #if aprogram.slewAt+aplen/86.4e3 < program.slewAt:
                self._debuglog.warning('Choose program with priority %i'%p)
                # put program back with same priority
                #self.rq.put((prt,program))
                # return alternate program
                return aprogram
            if not self.checkConditions(program,program.slewAt):
                program,plen = aprogram,aplen
            #program,plen,priority = aprogram,aplen,p
            #if not program.slewAt :
            #    # Program should be done right now if possible!
            #    # TEST "if possible"
            #    log.debug('Choose program with priority %i'%p)
            #    return program

        if program and not self.checkConditions(program,program.slewAt):
            # if project cannot be executed return nothing.
            # [TO-CHECK] What the scheduler will do? should sleep for a while and
            # [TO-CHECK] try again.
            return None

        self._debuglog.warning('Choose program with priority %i'%priority)
        return program

    def getProgram(self, nowmjd, priority):

        session = RSession()

        self._debuglog.debug('Looking for program with priority %i to observe @ %.3f '%(priority,nowmjd))

        program1 = session.query(Program).filter(Program.finished == False).filter(Program.priority == priority).filter(Program.slewAt > nowmjd).order_by(Program.slewAt).first()

        program2 = session.query(Program).filter(Program.finished == False).filter(Program.priority == priority).filter(Program.slewAt <= nowmjd).order_by(Program.slewAt.desc()).first()

        if not program1 and not program2:
            self._debuglog.debug('No program in alternate queue %i'%priority)
            session.commit()
            return None,-1

        elif not program1:
            self._debuglog.debug('No program1 in alternate queue %i'%priority)
            dT = 0
            for ii,act in enumerate(program2.actions):
                if ii > 0:
                    dT+=act.exptime*act.frames
            session.commit()
            return program2,dT

        elif not program2:
            self._debuglog.debug('No program2 in alternate queue %i'%priority)
            dT = 0
            for ii,act in enumerate(program1.actions):
                if ii > 0:
                    dT+=act.exptime*act.frames
            session.commit()
            return program1,dT

        self._debuglog.debug('Found 2 suitable programs in alternate queue %i'%priority)

        # Still need to check sky condition (seeing, moon, sky transparency....), altitude, moon...

        wtime1 = (program1.slewAt-nowmjd)
        wtime2 = (nowmjd-program2.slewAt)

        if wtime1 < wtime2:
            self._debuglog.debug('Program1 closer')
            dT = 0
            for ii,act in enumerate(program1.actions):
                if ii > 0:
                    dT+=act.exptime*act.frames
            session.commit()
            return program1,dT
        else:
            self._debuglog.debug('Program2 closer')
            dT = 0
            for ii,act in enumerate(program2.actions):
                if ii > 0:
                    dT+=act.exptime*act.frames
            session.commit()
            return program2,dT

    def getPList(self):

        session = Session()
        plist = [p[0] for p in session.query(Program.priority).distinct().order_by(Program.priority)]
        session.commit()

        return plist

    def checkConditions(self, prg, time):
        '''
        Check if a program can be executed given all restrictions imposed by airmass, moon distance,
         seeing, cloud cover, etc...

        [comment] There must be a good way of letting the user rewrite this easily. I can only
         think about a decorator but I am not sure how to implement it.

        :param program:
        :return: True (Program can be executed) | False (Program cannot be executed)
        '''

        site = self.getSite()
        # 1) check airmass
        session = RSession()
        program = session.merge(prg)
        target = session.query(Targets).filter(Targets.id == program.tid).first()
        blockpar = session.query(BlockPar).filter(BlockPar.pid == program.pid).filter(BlockPar.bid == program.blockid).first()

        raDec = Position.fromRaDec(target.targetRa,target.targetDec)

        dateTime = datetimeFromJD(time+2400000.5)
        lst = site.LST_inRads(dateTime) # in radians

        alt = float(site.raDecToAltAz(raDec,lst).alt)
        airmass = 1./np.cos(np.pi/2.-alt*np.pi/180.)

        if blockpar.minairmass < airmass < blockpar.maxairmass:
            self._debuglog.debug('\tairmass:%.3f'%airmass)
            pass
        else:
            self._debuglog.warning('Target %s out of range airmass... (%f < %f < %f)'%(target, blockpar.minairmass, airmass, blockpar.maxairmass))
            return False

        # 2) check moon Brightness

        moonBrightness = site.moonphase(dateTime)*100.
        if blockpar.minmoonBright < moonBrightness < blockpar.maxmoonBright:
            self._debuglog.debug('\tmoonBrightness:%.2f'%moonBrightness)
            pass
        else:
            self._debuglog.warning('Wrong Moon Brightness... (%f < %f < %f)'%(blockpar.minmoonBright,
                                                                   moonBrightness,
                                                                   blockpar.maxmoonBright))
            return False

        # 3) check moon distance
        moonRaDec = site.altAzToRaDec(site.moonpos(dateTime),lst)

        moonDist = raDec.angsep(moonRaDec)

        if moonDist < blockpar.minmoonDist:
            self._debuglog.warning('Object to close to the moon... '
                                   'Target@ %s / Moon@ %s (moonDist = %f | minmoonDist = %f)'%(raDec,
                                                                                               moonRaDec,
                                                                                               moonDist,
                                                                                               blockpar.minmoonDist))
            return False
        else:
            self._debuglog.debug('\tMoon distance:%.3f'%moonDist)
        # 4) check seeing

        if self["seeingmonitos"] is not None:

            seeing = self.getSM().seeing()

            if seeing > blockpar.maxseeing:
                self._debuglog.warning('Seeing higher than specified... sm = %f | max = %f'%(seeing,
                                                                                  blockpar.maxseeing))
                return False
            elif seeing < 0.:
                self._debuglog.warning('No seeing measurement...')
            else:
                self._debuglog.debug('Seeing %.3f'%seeing)
        # 5) check cloud cover
        if self["cloudsensors"] is not None:
            pass

        if self["weatherstations"] is not None:
            pass

        self._debuglog.debug('Target OK!')

        return True
