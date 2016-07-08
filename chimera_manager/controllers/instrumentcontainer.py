from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.event import event
from chimera.core.log import fmt
from chimera.controllers.scheduler.states import State as SchedState
from chimera.controllers.scheduler.status import SchedulerStatus as SchedStatus
from chimera.core.exceptions import ChimeraException

import threading
import telnetlib
import telegram
import logging
import time
from collections import OrderedDict

class InstrumentContainerException(ChimeraException):
    pass

class InstrumentContainer(ChimeraObject):

    __config__ = {'i_list' : [],
                  'i_type' : ''}

    def __init__(self):

        ChimeraObject.__init__(self)

        self._instrument_proxy_list = []
        self._current_selection = None

    def __start__(self):

        if len(self["instrument_list"]) > 0:
            self._current_selection = 0
        else:
            raise InstrumentContainerException("No instrument given. Container requires at least one instrument")

        for inst in self["instrument_list"]:
            self._instrument_proxy_list.append(self.controller.getManager().getProxy(self.controller.getLocation()))

    def select_instrument(self,index):
        if index < len(self._instrument_proxy_list):
            self._current_selection = index
        else:
            self.log.error("Could not set the specified instrument.")

    def __getattr__(self, item):
        return getattr(self._instrument_proxy_list[self._current_selection],item)

