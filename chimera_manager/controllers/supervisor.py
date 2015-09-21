# This is an example of an simple instrument.

import os

from chimera_manager.controllers.machine import Machine
from chimera_manager.controllers.checklist import CheckList
from chimera_manager.controllers.status import OperationStatus
from chimera_manager.controllers.states import State

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.event import event
from chimera.core.log import fmt

import threading
import telnetlib
import logging

class Supervisor(ChimeraObject):

    __config__ = {  "telegram-ip": None,       # Telegram host IP
                    "telegram-port": None,     # Telegram host port
                    "telegram-timeout": None,  # Telegram host timeout
                    "freq": 0.01               # Set manager watch frequency in Hz.
                 }

    def __init__(self):
        ChimeraObject.__init__(self)

        self._operationStatus = None

        self._telegramBroadcast = False
        self._telegramSocket = None
        self._testIP = '8.8.8.8' # Use google's dns IP as beacon to network connectivity

        self._log_handler = None

        self.checklist = None
        self.machine = None


    def __start__(self):

        self._openLogger()

        # Connect to telegram, if info is given
        self.connectTelegram()

        self.checklist = CheckList(self)
        self.machine = Machine(self.checklist, self)

        self.setHz(self["freq"])

    def __stop__(self):

        self.machine.state(State.SHUTDOWN)
        self.checklist.mustStop.set()

        if self.isTelegramConnected():
            self.disconnectTelegram()

        self._closeLogger()

    def control(self):

        self.log.debug('[control] current status is "%s"'%(self._operationStatus))

        if self.machine.state() == State.IDLE:
            self.machine.state(State.START)
            return True
        else:
            self.log.info("[control] current machine state is %s."%self.machine.state())

        if not self.machine.isAlive():
            self.machine.start()

        return True


    def connectTelegram(self):

        if self.isTelegramConnected():
            self.disconnectTelegram()

        if self["telegram-ip"] and self["telegram-port"]:
            self._telegramSocket = telnetlib.Telnet(self["telegram-ip"],
                                                    self["telegram-port"],
                                                    self["telegram-timeout"] if self["telegram-timeout"] is not None else 30)
            self.log.debug('[telegram]: Going online...')
            self._telegramSocket.write("status_online \r\n")
            if self._telegramSocket.expect(["SUCCESS"], timeout=5)[1]:
                self.log.debug("[telegram]: online SUCCESS")
                self._telegramBroadcast = True
            else:
                self.log.warning("[telegram]: online FAILED")
                self._telegramBroadcast = False

    def disconnectTelegram(self):
        try:
            self._telegramSocket.close()
        except Exception, e:
            # just log the exception
            self.log.exception(e)
        finally:
            self._telegramBroadcast = False
            self._telegramSocket = None


    def isTelegramConnected(self):
        return self._telegramSocket is not None

    def _openLogger(self):

        if self._log_handler:
            self._closeLogger()

        self._log_handler = logging.FileHandler(os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                                             "supervisor.log"))

        # self._log_handler.setFormatter(logging.Formatter(fmt='%(asctime)s.%(msecs)d %(origin)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s'))
        self._log_handler.setLevel(logging.DEBUG)
        self.log.addHandler(self._log_handler)

    def _closeLogger(self):
        if self._log_handler:
            self.log.removeHandler(self._log_handler)
            self._log_handler.close()

    def getLogger(self):
        return self._log_handler

    def broadCast(self,msg):
        self.log.info(msg)
        if self._telegramBroadcast:
            self._telegramSocket.write(msg+'\r\n')

    def site(self):
        return self.getManager().getProxy('/Site/0')

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
    def itemResponseComplete(self,item,response):
        pass
