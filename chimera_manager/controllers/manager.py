# This is an example of an simple instrument.

from chimera.core.chimeraobject import ChimeraObject

import threading
import telnetlib

class Manager(ChimeraObject):

    __config__ = {  "max_wind": 60,            # maximum allowed wind speed in km/h
                    "max_humidity": 85,        # maximum allowed external humidity in %
                    "min_temp": 1.0,           # minimum allowed external temperature in Celsius
                    "min_dewpoint": 3.0,       # minimum allowed external dew point temperature in Celsius
                    "min_sun_alt": -18,        # Sun altitude at the beginning/end of the night in degrees
                                               # (when the observations should start/end)
                    "close_on_none": True,     # Close if there is no information about the weather
                    "close_on_network": True,  # Close if there is no network connectivity
                    "scheduler_script": None,  # Command line path to the scheduler script. This is executed after the
                                               # end of the night clean up in preparation for next night
                    "telegram-ip": None,       # Telegram host IP
                    "telegram-port": None,     # Telegram host port
                    "telegram-timeout": None,  # Telegram host timeout
                    "freq": 0.01               # Set manager watch frequency in Hz.
                 }

    def __init__(self):
        ChimeraObject.__init__(self)

        self._telegramBroadcast = False
        self._telegramSocket = None
        self._testIP = '8.8.8.8' # Use google's dns IP as beacon to network connectivity

        self._abort = threading.Event()

    def __start__(self):

        # Connect to telegram, if info is given
        self.connectTelegram()

        # Get list of available weather stations
        self._weatherStations = self.getManager().getResourcesByClass("WeatherStation")
        self._nWS = len(self._weatherStations)

        if self._nWS == 0:
            self.log.warning("No Weather Station is available. Manager will be cripple without weather information.")
            if self["close_on_none"]:
                self.log.error("Manager cannot operate in 'close_on_none' mode without a weather station. Switching to cripple mode!")
                self["close_on_none"] = False

        self.setHz(self["freq"])

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

