
import os

from chimera_manager.controllers.machine import Machine
from chimera_manager.controllers.checklist import CheckList
from chimera_manager.controllers.status import OperationStatus, InstrumentOperationFlag
from chimera_manager.controllers.states import State
from chimera_manager.core.exceptions import StatusUpdateException

from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.event import event
from chimera.core.log import fmt
from chimera.controllers.scheduler.states import State as SchedState
from chimera.controllers.scheduler.status import SchedulerStatus as SchedStatus

import threading
import telnetlib
import telegram
import logging
import time
from collections import OrderedDict

class Supervisor(ChimeraObject):

    __config__ = {  "site"       : "/Site/0",
                    "telescope"  : "/Telescope/0",
                    "camera"     : "/Camera/0",
                    "dome"       : "/Dome/0",
                    "scheduler"  : None,
                    "domefan"    : None,
                    "weatherstations" : None,
                    "telegram-token": None,          # Telegram bot token
                    "telegram-broascast-ids": None,  # Telegram broadcast ids
                    "telegram-listen-ids": None,     # Telegram listen ids
                    "freq": 0.01  ,                  # Set manager watch frequency in Hz.
                    "max_mins": 10                   # Maximum time, in minutes, data from weather station should have
                 }

    def __init__(self):
        ChimeraObject.__init__(self)


        self._base_instrument_list = ["site", "telescope", "camera", "dome", "scheduler", "domefan", "weatherstations"]
        self._instrument_list = {}

        self._operationStatus = OrderedDict()

        # self._operationStatus = {
        #                          "site":            [ InstrumentOperationFlag.UNSET, ] ,
        #                          "telescope":       [ InstrumentOperationFlag.UNSET, ] ,
        #                          "camera":          [ InstrumentOperationFlag.UNSET, ] ,
        #                          "dome":            [ InstrumentOperationFlag.UNSET, ] ,
        #                          "scheduler":       [ InstrumentOperationFlag.UNSET, ] ,
        #                          "domefan":         [ InstrumentOperationFlag.UNSET, ] ,
        #                          "weatherstation":  [ InstrumentOperationFlag.UNSET, ] ,
        #                          }

        self._telegramBroadcast = False
        self._telegramSocket = None
        self._testIP = '8.8.8.8' # Use google's dns IP as beacon to network connectivity

        self._log_handler = None

        self.checklist = None
        self.machine = None
        self.bot = None


    def __start__(self):

        self._openLogger()

        # Connect to telegram, if info is given
        self.connectTelegram()

        # Configure instrument list
        for instrument in self._base_instrument_list:
            if self[instrument] is not None:
                self.log.debug('%s: %s -> %s' % (instrument,self[instrument],self[instrument].split(',')))
                self._instrument_list[instrument] = self[instrument].split(",")

                if len(self._instrument_list[instrument]) == 1:
                    self._operationStatus[instrument] = InstrumentOperationFlag.UNSET
                else:
                    for i, ainstrument in enumerate(self._instrument_list[instrument]):
                        self._operationStatus[instrument+'_%02i' % (i+1)] = InstrumentOperationFlag.UNSET

        self.checklist = CheckList(self)
        self.machine = Machine(self.checklist, self)

        # Connect to telescope events
        self._connectTelescopeEvents()

        # Connect to dome events
        self._connectDomeEvents()

        # Connect to scheduler events
        self._connectSchedulerEvents()

        self.setHz(self["freq"])

        self._broadcast_ids = None if self["telegram-broascast-ids"] is None \
            else [int(id) for id in str(self["telegram-broascast-ids"]).split(',')]

        self._listen_ids = None if self["telegram-listen-ids"] is None \
            else [int(id) for id in str(self["telegram-listen-ids"]).split(',')]


    def __stop__(self):

        self.machine.state(State.SHUTDOWN)
        self.checklist.mustStop.set()

        if self.isTelegramConnected():
            self.disconnectTelegram()

        self._closeLogger()

    def control(self):

        # self.log.debug('[control] current status is "%s"'%(self._operationStatus["site"]))

        if self.machine.state() == State.IDLE:
            self.machine.state(State.START)
            return True
        # else:
        #     self.log.info("[control] current machine state is %s."%self.machine.state())

        if not self.machine.isAlive():
            self.machine.start()

        # Todo: after starting the checker machine, do some basic check of operational status.

        return True

    def wakeup(self):
        if self.machine.state() == State.IDLE:
            self.machine.state(State.START)
            return True
        else:
            return False

    def start(self):
        if self.machine.state() == State.OFF:
            self.machine.state(State.IDLE)
            return True
        else:
            return False

    def stop(self):
        if self.machine.state() != State.OFF:
            self.machine.state(State.STOP)
            return True
        else:
            return False

    def runAction(self, name):
        return self.machine.runAction(name)

    def connectTelegram(self):

        if self["telegram-token"] is not None:
            self.bot = telegram.Bot(token=self["telegram-token"])

    def disconnectTelegram(self):
        pass

    def isTelegramConnected(self):
        return self._telegramSocket is not None

    def _openLogger(self):

        if self._log_handler:
            self._closeLogger()

        self._log_handler = logging.FileHandler(os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                                             "supervisor.log"))

        # self._log_handler.setFormatter(logging.Formatter(fmt='%(asctime)s.%(msecs)d %(origin)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s'))
        self._log_handler.setFormatter(logging.Formatter(fmt='%(asctime)s[%(levelname)8s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
        self._log_handler.setLevel(logging.DEBUG)
        self.log.addHandler(self._log_handler)

    def _closeLogger(self):
        if self._log_handler:
            self.log.removeHandler(self._log_handler)
            self._log_handler.close()

    def getLogger(self):
        return self._log_handler

    def broadCast(self,msg):
        if isinstance(msg,Exception):
            self.log.exception(msg)
            msg = repr(msg)
        else:
            self.log.info(msg)

        if self.bot is not None and self["telegram-broascast-ids"] is not None:
            for id in self._broadcast_ids:
                self.bot.sendMessage(chat_id=id,
                                     text=msg)

    def askWatcher(self,question,waittime):

        if self.bot is not None and self["telegram-listen-ids"] is not None:

            updates = self.bot.getUpdates()
            update_id=None
            for update in updates:
                update_id = updates[-1].update_id + 1

            self.log.debug('Asking lister %s.' % question)

            for id in self._listen_ids:
                self.bot.sendMessage(chat_id=id,
                                     text='[waittime: %i s] %s' %
                                          (waittime,
                                           question))

            start_time = time.time()
            while time.time() - start_time < waittime:

                updates = self.bot.getUpdates(offset = update_id)

                for update in updates:

                    if update.message.chat_id in self._listen_ids:
                        answer = update.message.text
                        if answer is not None:
                            return answer
                        update_id = update.update_id+1

            return None

    def site(self):
        return self.getManager().getProxy('/Site/0')

    def getInstrumentLocationList(self, instrument):
        return self._instrument_list[instrument]

    def getTel(self,index=0):
        return self.getManager().getProxy(self._instrument_list["telescope"][index])

    def getSched(self,index=0):
        return self.getManager().getProxy(self._instrument_list["scheduler"][index])

    def getSched(self):
        return self.getManager().getProxy(self["scheduler"])

    def getItems(self):
        return self.checklist.itemsList

    def getResponses(self):
        return self.checklist.responseList

    def getInstrumentList(self):
        return self._operationStatus.keys()

    def setFlag(self, instrument, flag, updatedb= True):
        if updatedb:
            if self.checklist.updateInstrumentStatus(instrument,flag):
                self._operationStatus[instrument] = flag
            else:
                raise StatusUpdateException("Could not update %s status with flag %s"%(instrument,
                                                                                       flag))
        else:
            self._operationStatus[instrument] = flag

    def getFlag(self,instrument):
        return self._operationStatus[instrument]

    def canOpen(self,instrument=None):
        """
        Checks if open operation are allowed in general or for a particular instrument. If none is given will only
        allow if all instruments have the open flag. Otherwise will check the instrument and site.

        :return:
        """

        if instrument is None:
            flag = True
            for inst_ in self._operationStatus.keys():
                flag = flag and ( (self.getFlag(inst_) == InstrumentOperationFlag.READY) or
                                  (self.getFlag(inst_) == InstrumentOperationFlag.OPERATING) )
            return flag
        else:
            return (self.getFlag(instrument) == InstrumentOperationFlag.READY) and \
                   (self.getFlag("site") == InstrumentOperationFlag.READY)


    def lockInstrument(self,instrument,key):

        if self.checklist.updateInstrumentStatus(instrument,
                                                 InstrumentOperationFlag.LOCK,
                                                 key):
            self._operationStatus[instrument] = InstrumentOperationFlag.LOCK
        else:
            self.log.warning("Could not change instrument status.")

    def getInstrumentKey(self,instrument):
        if self.getFlag(instrument) == InstrumentOperationFlag.LOCK:
            return self.checklist.instrumentKey(instrument)
        else:
            return ""

    def unlockInstrument(self,instrument,key):

        if self.getFlag(instrument) != InstrumentOperationFlag.LOCK:
            self.log.debug("Instrument not locked")
            return False

        if self.checklist.updateInstrumentStatus(instrument,
                                                 InstrumentOperationFlag.CLOSE,
                                                 key):
            self._operationStatus[instrument] = InstrumentOperationFlag.CLOSE
            return True
        else:
            raise StatusUpdateException("Unable to unlock %s with provided key"%(instrument))

    def activate(self,item):
        self.checklist.activate(item)

    def deactivate(self,item):
        self.checklist.deactivate(item)

    def _connectTelescopeEvents(self):
        # Todo
        tel = self.getTel()
        if not tel:
            self.log.warning("Couldn't find telescope.")
            return False

        tel.slewBegin += self.getProxy()._watchSlewBegin
        tel.slewComplete += self.getProxy()._watchSlewComplete
        tel.trackingStarted += self.getProxy()._watchTrackingStarted
        tel.trackingStopped += self.getProxy()._watchTrackingStopped
        tel.parkComplete += self.getProxy()._watchTelescopePark
        tel.unparkComplete += self.getProxy()._watchTelescopeUnpark

        return True

    def _connectSchedulerEvents(self):

        sched = self.getSched()
        if not sched:
            self.log.warning("Couldn't find telescope.")
            return False

        sched.programBegin += self.getProxy()._watchProgramBegin
        sched.programComplete += self.getProxy()._watchProgramComplete
        # sched.actionBegin += self.getProxy()._watchActionBegin
        # sched.actionComplete += self.getProxy()._watchActionComplete
        sched.stateChanged += self.getProxy()._watchStateChanged


    def _disconnectTelescopeEvents(self):
        tel = self.getTel()
        if not tel:
            self.log.warning("Couldn't find telescope.")
            return False

        tel.slewBegin -= self.getProxy()._watchSlewBegin
        tel.slewComplete -= self.getProxy()._watchSlewComplete
        tel.trackingStarted -= self.getProxy()._watchTrackingStarted
        tel.trackingStopped -= self.getProxy()._watchTrackingStopped
        tel.parkComplete -= self.getProxy()._watchTelescopePark
        tel.unparkComplete -= self.getProxy()._watchTelescopeUnpark

    def _disconnectSchedulerEvents(self):

        sched = self.getSched()
        if not sched:
            self.log.warning("Couldn't find telescope.")
            return False

        sched.programBegin -= self.getProxy()._watchProgramBegin
        sched.programComplete -= self.getProxy()._watchProgramComplete
        # sched.actionBegin -= self.getProxy()._watchActionBegin
        # sched.actionComplete -= self.getProxy()._watchActionComplete
        sched.stateChanged -= self.getProxy()._watchStateChanged

    def _connectDomeEvents(self):
        # Todo
        pass

    def _disconnectDomeEvents(self):
        # Todo
        pass

    def _watchSlewBegin(self, target):
        self.setFlag("telescope",InstrumentOperationFlag.OPERATING)

    def _watchSlewComplete(self, position, status):
        pass

    def _watchTrackingStarted(self, position):
        # Todo
        pass

    def _watchTrackingStopped(self, position, status):
        self.setFlag("telescope",InstrumentOperationFlag.READY)

    def _watchTelescopePark(self):

        self.broadCast("Telescope parked")
        self.setFlag("telescope",InstrumentOperationFlag.CLOSE)
        self.setFlag("dome",InstrumentOperationFlag.CLOSE)

    def _watchTelescopeUnpark(self):

        self.broadCast("Telescope unparked")
        self.setFlag("telescope",InstrumentOperationFlag.READY)
        self.setFlag("dome",InstrumentOperationFlag.READY)

    def _watchProgramBegin(self,program):
        if self.getFlag("scheduler") != InstrumentOperationFlag.OPERATING:
            self.setFlag("scheduler",InstrumentOperationFlag.OPERATING)

    def _watchProgramComplete(self, program, status, message=None):
        if status == SchedStatus.ERROR:
            msg = "Scheduler in ERROR"
            if message is not None:
                msg += ": %s" % message
            self.broadCast(msg)
            self.setFlag("scheduler",InstrumentOperationFlag.ERROR)
            # should I take any action regarding the telescope or even the scheduler itself?
            # Maybe stop the telescope? park the telescope? Or, I could have an action that, if the scheduler is in
            # error it will ask if it should close the telescope. Then, in the next cycle the action will take effect
        elif status == SchedStatus.ABORTED:
            self.setFlag("scheduler",InstrumentOperationFlag.READY)
            if message is not None:
                self.broadCast('%s' % message)

    def _watchStateChanged(self, newState, oldState):

        if newState == SchedState.BUSY:
            self.setFlag("scheduler",InstrumentOperationFlag.OPERATING)
        else:
            self.setFlag("scheduler",InstrumentOperationFlag.READY)

    @lock
    def status(self,new=None):
        if not new:
            return self._operationStatus
        self._operationStatus = new
        return

    @event
    def statusChanged(self,old,new):
        '''
        Wake all calls for checking their conditions.
        :return:
        '''
        pass

    @event
    def checkBegin(self,item):
        pass

    @event
    def checkComplete(self,item,status):
        pass

    @event
    def itemStatusChanged(self,item,status):
        pass

    @event
    def itemResponseBegin(self,item,response):
        pass


    @event
    def itemResponseComplete(self,item,response,status):
        pass
