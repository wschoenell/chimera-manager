from chimera.controllers.scheduler.states import State
from chimera.controllers.scheduler.model import Session, Program
from chimera.controllers.scheduler.status import SchedulerStatus

from chimera.core.exceptions import ProgramExecutionException, ProgramExecutionAborted

from chimera.core.site import Site

import threading
import logging

import time

# log = logging.getLogger(__name__.replace('chimera_manager','chimera.robobs'))

class Machine(threading.Thread):

    __state = None
    __stateLock = threading.Lock()
    __wakeUpCall = threading.Condition()

    def __init__(self, controller):
        threading.Thread.__init__(self)

        self.controller = controller

        self.currentProgram = None

        self.setDaemon(False)

    def state(self, state=None):
        log = self.controller.getLogger()
        self.__stateLock.acquire()
        try:
            if not state: return self.__state
            if state == self.__state: return
            # self.controller.stateChanged(state, self.__state)
            log.debug("Changing state, from %s to %s." % (self.__state, state))
            self.__state = state
            self.wakeup()
        finally:
            self.__stateLock.release()

    def run(self):
        log = self.controller.getLogger()
        log.info("Starting robobs machine")
        sched = self.controller.getSched()

        self.state(State.OFF)

        while self.state() != State.SHUTDOWN:

            if self.state() == State.OFF:
                log.debug("[off] will just sleep..")
                self.sleep()

            elif self.state() == State.START:
                log.debug("[start] waking scheduler...")
                # for i in range(10):
                #     log.debug('Waiting %i...' % i)
                #     time.sleep(1)

                sched.start()
                self.state(State.BUSY)

            elif self.state() == State.SHUTDOWN:
                log.debug("[shutdown] should die soon.")
                break

        log.debug('[shutdown] thread ending...')

    def sleep(self):
        log = self.controller.getLogger()
        self.__wakeUpCall.acquire()
        log.debug("Sleeping")
        self.__wakeUpCall.wait()
        self.__wakeUpCall.release()

    def wakeup(self):
        log = self.controller.getLogger()
        self.__wakeUpCall.acquire()
        log.debug("Waking up")
        self.__wakeUpCall.notifyAll()
        self.__wakeUpCall.release()

