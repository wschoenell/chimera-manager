
from chimera_manager.controllers.states import State
from chimera_manager.controllers.model import Session, List
from chimera_manager.controllers.status import OperationStatus
from chimera_manager.core.exceptions import CheckAborted

from chimera.core.site import Site

import threading
import logging

import time

log = logging.getLogger(__name__.replace("_manager",".supervisor"))

class Machine(threading.Thread):

    __state = State.OFF
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
            self.controller.statusChanged(state, self.__state)
            log.debug("Changing state, from %s to %s." % (self.__state, state))
            self.__state = state
            self.wakeup()
        finally:
            self.__stateLock.release()

    def run(self):
        log.info("Starting manager machine")
        self.state(State.IDLE)

        # inject instruments on handlers
        self.checklist.__start__()

        while self.state() != State.SHUTDOWN:

            if self.state() == State.OFF:
                log.debug("[off] will just sleep..")
                self.sleep()

            if self.state() == State.START:
                log.debug("[start] running checklist...")

                # Run checklist
                self.state(State.BUSY)
                self._process()

            elif self.state() == State.IDLE:
                log.debug("[idle] waiting for wake-up call..")
                self.sleep()

            elif self.state() == State.BUSY:
                log.debug("[busy] waiting tasks to finish..")
                self.sleep()

            elif self.state() == State.STOP:
                log.debug("[stop] trying to stop current program")
                self.checklist.mustStop.set()
                self.state(State.OFF)

            elif self.state() == State.SHUTDOWN:
                log.debug("[shutdown] trying to stop current program")
                self.checklist.mustStop.set()
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

    def _process(self):

        def process ():

            # session to be used by executor and handlers
            session = Session()

            checklist = None
            try:
                checklist = session.query(List)
            except Exception, e:
                log.exception(e)
                self.state(State.OFF)
                return

            log.debug("[start] processing %i items" % checklist.count())

            for item in checklist:
                try:
                    log.debug("[start] Checking %s"%item)
                    self.checklist.check(item)
                except CheckAborted:
                    self.state(State.OFF)
                    log.debug("[aborted by user] %s" % str(item))
                    break
                except Exception, e:
                    log.exception(e)
                    pass
            session.commit()
            self.state(State.IDLE)

        t = threading.Thread(target=process)
        t.setDaemon(False)
        t.start()
