
from chimera_manager.controllers.handlers import TimeHandler

import threading
import collections

class CheckList(object):

    def __init__(self, controller):

        self.mustStop = threading.Event()

        self.controller = controller
        self.checkHandlers = {}

        self._checkList = collections.OrderedDict()