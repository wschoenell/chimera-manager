import sys,os
import logging
import shutil
import time
import numpy as np
import threading
import inspect

from chimera_manager.controllers.scheduler.model import Session as RSession
from chimera_manager.controllers.scheduler.model import (Program, Targets, BlockPar, ObsBlock,
                                                         ObservingLog, AutoFocus, Point, Expose)
from chimera_manager.controllers.scheduler.machine import Machine
from chimera_manager.controllers.scheduler import algorithms

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

schedAlgorithms = {}
for name,obj in inspect.getmembers(algorithms):
    if inspect.isclass(obj) and issubclass(obj,algorithms.BaseScheduleAlgorith):
        schedAlgorithms[obj.id()] = obj

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

        self._injectInstrument()

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
        site = self.getSite()
        rsession = RSession()
        log = ObservingLog(time=datetimeFromJD(site.mjd()+2400000.5,),
                             tid=program.tid,
                             name=program.name,
                             priority=program.priority,
                             action='ROBOBS: Program Started')
        rsession.add(log)
        rsession.commit()


    def _watchProgramComplete(self, program, status, message=None):

        session = model.Session()
        program = session.merge(program)
        self._debuglog.debug('Program %s completed with status %s(%s)' % (program,
                                                                    status,
                                                                    message))
        site = self.getSite()
        rsession = RSession()
        log = ObservingLog(time=datetimeFromJD(site.MJD()+2400000.5,),
                             tid=program.tid,
                             name=program.name,
                             priority=program.priority,
                             action='ROBOBS: Program End with status %s(%s)' % (status,
                                                                                message))
        rsession.add(log)
        rsession.commit()

        if status == SchedulerStatus.OK and self._current_program is not None:
            rsession = RSession()
            cp = rsession.merge(self._current_program[0])
            cp.finished = True
            rsession.commit()

            block_config = rsession.merge(self._current_program[1])
            sched = schedAlgorithms[block_config.schedalgorith]
            sched.observed(site.MJD(),self._current_program,
                           site)
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
                program_info = self.reshedule()
                #
                if program_info is not None:
                    program = session.merge(program_info[0])
                    obs_block = session.merge(program_info[2])
                    self._debuglog.debug("Adding program %s to sheduler and starting." % program)
                    cprogram = program.chimeraProgram()
                    for act in obs_block.actions:
                        cact = getattr(sys.modules[__name__],act.action_type).chimeraAction(act)
                        cprogram.actions.append(cact)
                    cprogram = csession.merge(cprogram)
                    csession.add(cprogram)
                    csession.commit()
                    program.finished = True
                    session.commit()
                    # sched = self.getSched()
                    self._current_program = program_info
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

    def reshedule(self,now=None):

        session = RSession()

        site = self.getSite()
        if now is None:
            nowmjd = site.MJD()
        else:
            nowmjd = now

        program = None

        # Get a list of priorities
        plist = self.getPList()

        if len(plist) == 0:
            return None

        # Get project with highest priority as reference
        priority = plist[0]
        program,plen = self.getProgram(nowmjd,plist[0])

        waittime=0

        if program is not None:
            # program = session.merge(program)
            if ( (not program[0].slewAt) and (self.checkConditions(program,nowmjd))):
                # Program should be done right away!
                return program

            self._debuglog.info('Current program length: %.2f m. Slew@: %.3f'%(plen/60.,program[0].slewAt))

            waittime=(program[0].slewAt-nowmjd)*86.4e3
        else:
            self._debuglog.warning('No program on %i priority queue.' % plist[0])

        if waittime < 0:
            waittime = 0

        self._debuglog.info('Wait time is: %.2f m'%(waittime/60.))

        for p in plist[1:]:

            # Get program and program duration (lenght)

            aprogram,aplen = self.getProgram(nowmjd,p)

            # aprogram = session.merge(aprogram)

            if not aprogram:
                continue

            if not program:
                program = aprogram

            if not self.checkConditions(aprogram,aprogram[0].slewAt):
                # if condition is False, project cannot be executed. Go to next in the list
                continue

            self._debuglog.info('Current program length: %.2f m. Slew@: %.3f'%(aplen/60.,aprogram[0].slewAt))
            #return program
            #if aplen < 0 and program:
            #	log.debug('Using normal program (aplen < 0)...')
            #	return program

            # If alternate program fits will send it instead

            awaittime=(aprogram[0].slewAt-nowmjd)*86.4e3

            if awaittime < 0:
                awaittime = 0

            self._debuglog.info('Wait time is: %.2f m'%(awaittime/60.))

            # if awaittime+aplen < waittime+plen:
            if awaittime < waittime:
            #if aprogram.slewAt+aplen/86.4e3 < program.slewAt:
                self._debuglog.info('Choose program with priority %i'%p)
                # put program back with same priority
                #self.rq.put((prt,program))
                # return alternate program
                session.commit()
                return aprogram
            if not self.checkConditions(program,program[0].slewAt):
                program,plen,waittime = aprogram,aplen,awaittime

            #program,plen,priority = aprogram,aplen,p
            #if not program.slewAt :
            #    # Program should be done right now if possible!
            #    # TEST "if possible"
            #    log.debug('Choose program with priority %i'%p)
            #    return program

        if program is None:
            # if project cannot be executed return nothing.
            # [TO-CHECK] What the scheduler will do? should sleep for a while and
            # [TO-CHECK] try again.
            session.commit()
            return None
        elif not self.checkConditions(program,program[0].slewAt):
            session.commit()
            return None

        self._debuglog.info('Choose program with priority %i'%priority)
        session.commit()
        return program

    def getProgram(self, nowmjd, priority):

        session = RSession()

        self._debuglog.debug('Looking for program with priority %i to observe @ %.3f '%(priority,nowmjd))

        programs = session.query(Program,
                                 BlockPar,
                                 ObsBlock,
                                 Targets).join(
            BlockPar,Program.blockpar_id == BlockPar.id).join(
            ObsBlock,Program.obsblock_id == ObsBlock.id).join(
            Targets, Program.tid == Targets.id).filter(Program.priority == priority,
                                                       Program.finished == False).order_by(Program.slewAt)

        schedAlgList = np.array([t[1].schedalgorith for t in programs])
        unique_shed_algorithm_list = np.unique(schedAlgList)

        mjd = self.getSite().MJD()
        dt = np.zeros(programs.count())

        prog = []
        for sAL in unique_shed_algorithm_list:

            # nquery = programs.filter(BlockPar.schedalgorith == sAL)

            sched = schedAlgorithms[sAL]

            program = sched.next(nowmjd,programs)

            if program is not None:
                self._debuglog.debug('Found program %s' % program[0])
                dT = 0.

                for ii,act in enumerate(program[2].actions):
                    if act.__tablename__ == 'action_expose':
                        dT+=act.exptime*act.frames
                session.commit()
                return program,dT

        self.log.warning('No program found...')
        session.commit()
        return None,0.


    def getPList(self):

        session = RSession()
        plist = [p[0] for p in session.query(Program.priority).distinct().order_by(Program.priority)]
        session.commit()

        return plist

    def checkConditions(self, program, time):
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
        # program = session.merge(prg)
        target = session.merge(program[3])
        # obsblock = session.merge(program[2])
        blockpar = session.merge(program[1])

        raDec = Position.fromRaDec(target.targetRa,target.targetDec)

        dateTime = datetimeFromJD(time+2400000.5)
        lst = site.LST_inRads(dateTime) # in radians

        alt = float(site.raDecToAltAz(raDec,lst).alt)
        airmass = 1./np.cos(np.pi/2.-alt*np.pi/180.)

        if blockpar.minairmass < airmass < blockpar.maxairmass:
            self._debuglog.debug('\tairmass:%.3f'%airmass)
            pass
        else:
            self._debuglog.warning('Target %s out of range airmass... (%f < %f < %f)'%(target,
                                                                                       blockpar.minairmass,
                                                                                       airmass,
                                                                                       blockpar.maxairmass))
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

    def _injectInstrument(self):

        for algorithm in schedAlgorithms.values():

            try:
                inst_manager = self.getManager().getProxy(self['site'])
                setattr(algorithm,'site',inst_manager)
            except Exception, e:
                self.log.error('Could not inject %s on %s handler' % ('site',
                                                                         algorithm))
                self.log.exception(e)



