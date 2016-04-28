
import os

from chimera_manager.controllers.machine import Machine
from chimera_manager.controllers.checklist import CheckList
from chimera_manager.controllers.status import OperationStatus, InstrumentOperationFlag
from chimera_manager.controllers.states import State
from chimera_manager.core.exceptions import StatusUpdateException
from chimera_manager.core.constants import SYSTEM_CONFIG_DIRECTORY

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.event import event
from chimera.core.log import fmt

import threading
import telnetlib
import telegram
import logging
import time

class Supervisor(ChimeraObject):

    __config__ = {  "site"       : "/Site/0",
                    "telescope"  : "/Telescope/0",
                    "camera"     : "/Camera/0",
                    "dome"       : "/Dome/0",
                    "scheduler"  : None,
                    "domefan"    : None,
                    "weatherstation" : None,
                    "telegram-token": None,          # Telegram bot token
                    "telegram-broascast-ids": None,  # Telegram broadcast ids
                    "telegram-listen-ids": None,     # Telegram listen ids
                    "freq": 0.01               # Set manager watch frequency in Hz.
                 }

    def __init__(self):
        ChimeraObject.__init__(self)

        self._operationStatus = {
                                 "site":            InstrumentOperationFlag.UNSET,
                                 "telescope":       InstrumentOperationFlag.UNSET,
                                 "camera":          InstrumentOperationFlag.UNSET,
                                 "dome":            InstrumentOperationFlag.UNSET,
                                 "scheduler":       InstrumentOperationFlag.UNSET,
                                 "domefan":         InstrumentOperationFlag.UNSET,
                                 "weatherstation":  InstrumentOperationFlag.UNSET,
                                 }

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
            for id in self["telegram-broascast-ids"]:
                self.bot.sendMessage(chat_id=id,
                                     text=msg)

    def askWatcher(self,question):

        if self.bot is not None and self["telegram-listen-ids"] is not None:

            updates = self.bot.getUpdates()
            update_id = updates[-1].message.update_id + 1

            self.log.debug('Asking lister %s.' % question.question)

            for id in self["telegram-listen-ids"]:
                self.bot.sendMessage(chat_id=id,
                                     text='[waittime: %i s] %s' %
                                          (question.waittime,
                                           question.question))

            start_time = time.time()
            while time.time() - start_time < question.waittime:

                updates = self.bot.getUpdates(offset = update_id)

                for update in updates:

                    if update.message.chat_id in self["telegram-listen-ids"]:
                        answer = update.message.text
                        if answer is not None:
                            return answer
                        update_id = update.message.update_id+1

            return None

    def site(self):
        return self.getManager().getProxy('/Site/0')

    def getTel(self):
        return self.getManager().getProxy(self["telescope"])

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
                flag = flag and (self.getFlag(inst_) == InstrumentOperationFlag.READY)
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

    def _watchSlewBegin(self):
        self.setFlag("telescope",InstrumentOperationFlag.OPERATING)

    def _watchSlewComplete(self):
        pass

    def _watchTrackingStarted(self):
        # Todo
        pass

    def _watchTrackingStopped(self):
        self.setFlag("telescope",InstrumentOperationFlag.READY)

    def _watchTelescopePark(self):

        self.broadCast("Telescope parked")
        self.setFlag("telescope",InstrumentOperationFlag.CLOSE)
        self.setFlag("dome",InstrumentOperationFlag.CLOSE)

    def _watchTelescopeUnpark(self):

        self.broadCast("Telescope unparked")
        self.setFlag("telescope",InstrumentOperationFlag.READY)
        self.setFlag("dome",InstrumentOperationFlag.READY)

    def _connectDomeEvents(self):
        # Todo
        pass

    def _disconnectDomeEvents(self):
        # Todo
        pass

    def _connectSchedulerEvents(self):
        # Todo
        pass

    def _disconnectSchedulerEvents(self):
        # Todo
        pass

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
