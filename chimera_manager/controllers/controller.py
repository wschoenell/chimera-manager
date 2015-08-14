# This is an example of an simple instrument.

import os

from chimera_manager.controllers.status import OperationStatus

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.event import event
from chimera.core.log import fmt

import threading
import telnetlib
import logging

class Manager(ChimeraObject):

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

        self._loghandler = None

        self._abort = threading.Event()

    def __start__(self):

        self._openLogger()

        # Connect to telegram, if info is given
        self.connectTelegram()

        # Get list of available weather stations
        self._weatherStations = self.getManager().getResourcesByClass("WeatherStation")
        self._nWS = len(self._weatherStations)

        if self._nWS == 0:
            self.log.warning("No Weather Station is available. Manager will be cripple without weather information.")
            if self["close_on_none"]:
                self.log.error("Manager cannot operate in 'close_on_none' mode without a weather station."
                               "Switching to cripple mode!")
                self["close_on_none"] = False

        self.setHz(self["freq"])

    def __stop__(self):

        if self.isTelegramConnected():
            self.disconnectTelegram()

        self._closeLogger()

    def control(self):

        self.log.debug('[control]: Current status is "%s"'%(self._operationStatus))

        status = self.checkTime()

        if status == OperationStatus.OPERATING:
            status = self.checkWeather()

        if status == OperationStatus.OPERATING:
            status == self.checkNetwork()

        if status != self._operationStatus:
            self.log.debug("[control]: Operation status changed %s -> %s"%(self._operationStatus,
                                                                           status))
            self.statusChanged(self._operationStatus,status)
        else:
            self.log.debug('[control]: Current status %s'%(status))

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
                                                             "manager.log"))

        self._log_handler.setFormatter(logging.Formatter(fmt=fmt))
        self._log_handler.setLevel(logging.DEBUG)
        self.log.addHandler(self._log_handler)

    def _closeLogger(self):
        if self._log_handler:
            self.log.removeHandler(self._log_handler)
            self._log_handler.close()

    def checkTime(self):
        return OperationStatus.CLOSED

    def checkWeather(self):
        return OperationStatus.CLOSED

    def checkNetwork(self):
        return OperationStatus.CLOSED

    def broadCast(self,msg):
        self.log.info(msg)
        if self._telegramBroadcast:
            self._telegramSocket.write(msg+'\r\n')

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