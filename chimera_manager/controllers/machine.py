
from chimera_manager.controllers.states import State
from chimera_manager.controllers.model import Session, List
from chimera_manager.controllers.status import OperationStatus

from chimera.core.site import Site

import threading
import logging

import time

log = logging.getLogger(__name__)

class Machine(threading.Thread):

    __state = None
    __stateLock = threading.Lock()
    __wakeUpCall = threading.Condition()

    def __init__(self, checklist, controller):
        threading.Thread.__init__(self)

        self.checklist = checklist
        self.controller = controller

        self.setDaemon(False)

    def state(self, state=None):
        self.__stateLock.acquire()
        try:
            if not state: return self.__state
            if state == self.__state: return
            self.controller.stateChanged(state, self.__state)
            log.debug("Changing state, from %s to %s." % (self.__state, state))
            self.__state = state
            self.wakeup()
        finally:
            self.__stateLock.release()

    def run(self):
        log.info("Starting manager machine")
        self.state(State.OFF)

        # inject instruments on handlers
        self.checklist.__start__()

        while self.state() != State.SHUTDOWN:

            if self.state() == State.OFF:
                log.debug("[off] will just sleep..")
                self.sleep()

            if self.state() == State.START:
                log.debug("[start] looking for something to do...")

                # Run checklist
                self.state(State.BUSY)
                status = self.checklist.run()
                if status != self.controller.

                self.state(State.OFF)

            elif self.state() == State.BUSY:
                log.debug("[busy] waiting tasks to finish..")
                self.sleep()

            elif self.state() == State.STOP:
                log.debug("[stop] trying to stop current program")
                self.executor.stop()
                self.state(State.OFF)

            elif self.state() == State.SHUTDOWN:
                log.debug("[shutdown] trying to stop current program")
                self.executor.stop()
                log.debug("[shutdown] should die soon.")
                break

        log.debug('[shutdown] thread ending...')

    def sleep(self):
        self.__wakeUpCall.acquire()
        log.debug("Sleeping")
        self.__wakeUpCall.wait()
        self.__wakeUpCall.release()

    def wakeup(self):
        self.__wakeUpCall.acquire()
        log.debug("Waking up")
        self.__wakeUpCall.notifyAll()
        self.__wakeUpCall.release()

    def restartAllPrograms(self):
        session = Session()

        programs = session.query(Program).all()
        for program in programs:
            program.finished = False

        session.commit()

    def _process(self, program):

        def process ():

            # session to be used by executor and handlers
            session = Session()

            task = session.merge(program)

            log.debug("[start] %s" % str(task))

            site=Site()
            nowmjd=site.MJD()
            log.debug("[start] Current MJD is %f",nowmjd)
            if program.slewAt:
                waittime=(program.slewAt-nowmjd)*86.4e3
                if waittime>0.0:
                    log.debug("[start] Waiting until MJD %f to start slewing",program.slewAt)
                    log.debug("[start] Will wait for %f seconds",waittime)
                    time.sleep(waittime)
                else:
                    log.debug("[start] Specified slew start MJD %s has already passed; proceeding without waiting",program.slewAt)
            else:
               log.debug("[start] No slew time specified, so no waiting")
            log.debug("[start] Current MJD is %f",site.MJD())
            log.debug("[start] Proceeding since MJD %f should have passed",program.slewAt)
            self.controller.programBegin(program)

            try:
                self.executor.execute(task)
                log.debug("[finish] %s" % str(task))
                self.scheduler.done(task)
                self.controller.programComplete(program, SchedulerStatus.OK)
                self.state(State.IDLE)
            except ProgramExecutionException, e:
                self.scheduler.done(task, error=e)
                self.controller.programComplete(program, SchedulerStatus.ERROR, str(e))
                self.state(State.IDLE)
                log.debug("[error] %s (%s)" % (str(task), str(e)))
            except ProgramExecutionAborted, e:
                self.scheduler.done(task, error=e)
                self.controller.programComplete(program, SchedulerStatus.ABORTED, "Aborted by user.")
                self.state(State.OFF)
                log.debug("[aborted by user] %s" % str(task))

            session.commit()

        t = threading.Thread(target=process)
        t.setDaemon(False)
        t.start()
