import sys,os
import logging
import shutil
import time
import numpy as np
import threading

from chimera_manager.controllers.scheduler.model import Session as RSession
from chimera_manager.controllers.scheduler.model import (Program, Targets, BlockPar, AutoFocus, Point, Expose)
from chimera_manager.controllers.scheduler.machine import Machine

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.site import datetimeFromJD
from chimera.core.event import event
from chimera.controllers.scheduler.states import State as SchedState
from chimera.controllers.scheduler.status import SchedulerStatus
from chimera.controllers.scheduler import model
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
        self._current_program = None
        self._current_program_condition = threading.Condition()
        self._debuglog = None
        self.machine = None

    def __start__(self):

        self.log.debug("here")

        self._scheduler_list = self["schedulers"].split(',')

        self._connectSchedulerEvents()

        self._debuglog = logging.getLogger('_robobs_debug_')
        logfile = os.path.join(SYSTEM_CONFIG_DIRECTORY, "robobs_%s.log"%time.strftime("%Y%m%d"))
        # if os.path.exists(logfile):
        #     shutil.move(logfile, os.path.join(SYSTEM_CONFIG_DIRECTORY,
        #                                       "robobs.log_%s"%time.strftime("%Y%m%d-%H%M%S")))

        _log_handler = logging.FileHandler(logfile)
        _log_handler.setFormatter(logging.Formatter(
            fmt='%(asctime)s[%(levelname)s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
        # _log_handler.setLevel(logging.DEBUG)
        self._debuglog.setLevel(logging.DEBUG)
        self._debuglog.addHandler(_log_handler)
        self.log.setLevel(logging.INFO)

        self.machine = Machine(self)
        self.machine.start()

    def __stop__(self):
        self._disconnectSchedulerEvents()
        self._debuglog.debug("Shuting down machine...")
        self.machine.state(SchedState.SHUTDOWN)

    def start(self):
        self._debuglog.debug("Switching robstate on...")
        self.rob_state = RobState.ON

        return True

    def stop(self):
        self._debuglog.debug("Switching robstate off...")
        self.rob_state = RobState.OFF

        return True

    def wake(self):
        self._debuglog.debug("Waking machine up...")
        self.machine.state(SchedState.START)

    def getSite(self):
        return self.getManager().getProxy(self["site"])

    def getSched(self,index=0):
        self.log.debug("%s" % self._scheduler_list[index])
        if self._debuglog is not None:
            self._debuglog.debug("%s" % self._scheduler_list[index])
        # return None
        return self.getManager().getProxy(self._scheduler_list[index])

    def _connectSchedulerEvents(self):
        sched = self.getSched()
        if not sched:
            self.log.warning("Couldn't find scheduler.")
            self._debuglog.warning("Couldn't find scheduler.")
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
            self._debuglog.warning("Couldn't find scheduler.")
            return False

        sched.programBegin -= self.getProxy()._watchProgramBegin
        sched.programComplete -= self.getProxy()._watchProgramComplete
        sched.actionBegin -= self.getProxy()._watchActionBegin
        sched.actionComplete -= self.getProxy()._watchActionComplete
        sched.stateChanged -= self.getProxy()._watchStateChanged

    def _watchProgramBegin(self,program):
        session = model.Session()
        program = session.merge(program)
        self._debuglog.debug('Program %s started' % program)

    def _watchProgramComplete(self, program, status, message=None):

        session = model.Session()
        program = session.merge(program)
        self._debuglog.debug('Program %s completed with status %s(%s)' % (program,
                                                                    status,
                                                                    message))
        if status == SchedulerStatus.OK and self._current_program is not None:
            rsession = RSession()
            cp = rsession.merge(self._current_program)
            cp.finished = True
            rsession.commit()
            self._current_program = None
        # self._current_program_condition.acquire()
        # for i in range(10):
        #     self._debuglog.debug('Sleeping %2i ...' % i)
        #     time.sleep(1)
        # self._current_program_condition.notifyAll()
        # self._current_program_condition.release()

    def _watchActionBegin(self,action, message):
        session = model.Session()
        action = session.merge(action)
        self._debuglog.debug("%s %s ..." % (action,message))


    def _watchActionComplete(self,action, status, message=None):
        session = model.Session()
        action = session.merge(action)

        if status == SchedulerStatus.OK:
            self._debuglog.debug("%s: %s" % (action,
                                            str(status)))
        else:
            self._debuglog.debug("%s: %s (%s)" % (action,
                                     str(status), str(message)))

    def _watchStateChanged(self, newState, oldState):

        self._debuglog.debug("State changed %s -> %s..." % (oldState,
                                                            newState))
        if oldState == SchedState.IDLE and newState == SchedState.OFF:
            if self.rob_state == RobState.ON:
                self._debuglog.debug("Scheduler went from BUSY to OFF. Needs resheduling...")

                # if self._current_program is not None:
                #     self._debuglog.warning("Wait for last program to be updated")
                #     self._current_program_condition.acquire()
                #     self._current_program_condition.wait(30) # wait 10s most!
                #     self._current_program_condition.release()
                session = RSession()
                csession = model.Session()

                # cprog = model.Program(  name =  "CALIB",
                #                         pi = "Tiago Ribeiro",
                #                         priority = 1 )
                # cprog.actions.append(model.Expose(frames = 3,
                #                                   exptime = 10,
                #                                   imageType = "DARK",
                #                                   shutter = "CLOSE",
                #                                   filename = "dark-$DATE-$TIME"))
                # cprog.actions.append(model.Expose(frames = 1,
                #                                   exptime = 0,
                #                                   imageType = "DARK",
                #                                   shutter = "CLOSE",
                #                                   filename = "bias-$DATE-$TIME"))
                #
                # csession.add(cprog)
                # self._current_program = cprog
                # self._debuglog.debug("Added: %s" % cprog)
                program = self.reshedule()
                program = session.merge(program)
                #
                if program is not None:
                    self._debuglog.debug("Adding program %s to sheduler and starting." % program)
                    cprogram = program.chimeraProgram()
                    for act in program.actions:
                        cact = getattr(sys.modules[__name__],act.action_type).chimeraAction(act)
                        cprogram.actions.append(cact)
                    cprogram = csession.merge(cprogram)
                    csession.add(cprogram)
                    csession.commit()
                    program.finished = True
                    session.commit()
                    # sched = self.getSched()
                    self._current_program = program
                    # sched.start()
                    # self._current_program_condition.release()
                    self._debuglog.debug("Done")
                else:
                    self._debuglog.debug("No program on robobs queue.")

                csession.commit()
                session.commit()
                # for i in range(10):
                #     self.log.debug('Waiting %i/10' % i)
                #     time.sleep(1.0)
                # sched = self.getSched()
                # sched.start()
                self.wake()
                self._debuglog.debug("Done")
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
            self._debuglog.info('Current program length: %.2f m. Slew@: %.3f'%(plen/60.,program.slewAt))

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

            self._debuglog.info('Current program length: %.2f m. Slew@: %.3f'%(aplen/60.,aprogram.slewAt))
            #return program
            #if aplen < 0 and program:
            #	log.debug('Using normal program (aplen < 0)...')
            #	return program

            # If alternate program fits will send it instead

            waittime=(program.slewAt-nowmjd)*86.4e3

            if waittime < 0:
                waittime = 0

            self._debuglog.info('Wait time is: %.2f m'%(waittime/60.))

            if waittime>aplen or waittime > 2.*plen:
            #if aprogram.slewAt+aplen/86.4e3 < program.slewAt:
                self._debuglog.info('Choose program with priority %i'%p)
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

        self._debuglog.info('Choose program with priority %i'%priority)
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

        session = RSession()
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

        if self["seeingmonitors"] is not None:

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

    def getLogger(self):
        return self._debuglog