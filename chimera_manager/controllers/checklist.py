
from chimera_manager.controllers.model import Session, List, CheckTime, Response
from chimera_manager.controllers.handlers import CheckHandler, TimeHandler
from chimera_manager.controllers import baseresponse
from chimera_manager.controllers.status import FlagStatus

from chimera.core.exceptions import ObjectNotFoundException
from chimera_manager.core.exceptions import CheckAborted,CheckExecutionException

import logging
import threading
import inspect
import time

log = logging.getLogger(__name__.replace("_manager",".supervisor"))

class CheckList(object):

    def __init__(self, controller):

        self.currentHandler  = None
        self.currentCheck    = None
        self.currentResponse = None

        self.mustStop = threading.Event()

        self.controller = controller
        self.checkHandlers = {CheckTime: TimeHandler}
        self.itemsList = {}
        self.responseList = {}

    def __start__(self):

        # configure items list
        from chimera_manager.controllers import model
        for name,obj in inspect.getmembers(model):
            if inspect.isclass(obj) and issubclass(obj,model.Check):
                self.itemsList[name.upper()] = obj

        # Configure handlers
        for handler in self.checkHandlers.values():
            self._injectInstrument(handler)

        # Configure base responses
        for name,obj in inspect.getmembers(baseresponse):
            if inspect.isclass(obj) and issubclass(obj,baseresponse.BaseResponse):
                self.responseList[name.upper()] = obj

        # Todo: Configure user-defined responses

        return

    def check(self, item):

        t0 = time.time()

        self.mustStop.clear()

        responseList = {}
        for response in item.response:
            responseList['%s.%s'%(response.id,response.list_id)] = response.response_type

        for check in item.check:

            # aborted?
            if self.mustStop.isSet():
                raise CheckAborted()


            try:
                self.currentCheck = check
                self.currentHandler = self.checkHandlers[type(check)]

                logMsg = str(self.currentHandler.log(check))
                log.debug("[start] %s " % logMsg)
                self.controller.checkBegin(check, logMsg)

                rid,status = self.currentHandler.process(check) # return response id

                # Check for abort flag
                if self.mustStop.isSet():
                    self.controller.checkComplete(check, FlagStatus.ABORTED)
                    raise CheckAborted()
                elif status != FlagStatus[item.status] or item.eager:
                    self.controller.itemStatusChanged(item,status)
                    # Get response
                    currentResponse = self.responseList['%s.%s'%(check.id,rid)]
                    self.currentResponse = self.responseList[currentResponse]
                    self.controller.itemResponseBegin(item,currentResponse)
                    self.currentResponse.process(check)
                    item.status = status.index
                    item.lastUpdate = self.controller.site().localtime()
                    self.controller.itemResponseComplete(item,currentResponse)
                    self.controller.checkComplete(check, FlagStatus.OK)

            except CheckExecutionException, e:
                self.controller.checkComplete(check, FlagStatus.ERROR)
                raise
            except KeyError:
                log.debug("No handler to %s item. Skipping it" % check)
            finally:
                log.debug("[finish] took: %f s" % (time.time() - t0))


    def _injectInstrument(self, handler):
        if not issubclass(handler, CheckHandler):
            return

        if not hasattr(handler.process, "__requires__"):
            return

        for instrument in handler.process.__requires__:
            try:
                setattr(handler, instrument,
                        self.controller.getManager().getProxy(self.controller[instrument]))
            except ObjectNotFoundException, e:
                log.error("No instrument to inject on %s handler" % handler)

