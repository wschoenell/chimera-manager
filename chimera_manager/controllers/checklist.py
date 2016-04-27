
from chimera_manager.controllers.model import (Session, List, CheckTime, CheckHumidity,
                                               CheckTemperature, CheckWindSpeed,
                                               CheckDewPoint, CheckDew,
                                               Response)
from chimera_manager.controllers.iostatus_model import Session as ioSession
from chimera_manager.controllers.iostatus_model import InstrumentOperationStatus

from chimera_manager.controllers.handlers import (CheckHandler, TimeHandler,
                                                  HumidityHandler, TemperatureHandler,
                                                  WindSpeedHandler, DewPointHandler,
                                                  DewHandler)
from chimera_manager.controllers import baseresponse
from chimera_manager.controllers.status import FlagStatus, ResponseStatus, InstrumentOperationFlag

from chimera.core.exceptions import ObjectNotFoundException, InvalidLocationException
from chimera_manager.core.exceptions import CheckAborted,CheckExecutionException

import logging
import threading
import inspect
import time

# log = logging.getLogger(__name__.replace("_manager",".supervisor"))

class CheckList(object):

    def __init__(self, controller):

        self.currentHandler  = None
        self.currentCheck    = None
        self.currentResponse = None

        self.mustStop = threading.Event()

        self.controller = controller
        self.log = controller.log
        
        self.checkHandlers = {CheckTime:        TimeHandler,
                              CheckHumidity:    HumidityHandler,
                              CheckTemperature: TemperatureHandler,
                              CheckWindSpeed:   WindSpeedHandler,
                              CheckDewPoint:    DewPointHandler,
                              CheckDew:         DewHandler,

                              }
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

        # Configure base responses handlers
        for handler in self.responseList.values():
            self._injectInstrument(handler)

        # Todo: Configure user-defined responses

        # Read instrument status flag from database
        session = ioSession()
        for inst_ in self.controller.getInstrumentList():
            status = session.query(InstrumentOperationStatus).filter(InstrumentOperationStatus.instrument == inst_)
            if status.count() == 0:
                self.log.warning("No %s intrument on database. Adding with status UNSET."%inst_)
                iostatus = InstrumentOperationStatus(instrument = inst_,
                                                     status = InstrumentOperationFlag.UNSET.index,
                                                     lastUpdate = self.controller.site().ut().replace(tzinfo=None),
                                                     lastChange = self.controller.site().ut().replace(tzinfo=None))
                session.add(iostatus)
                session.commit()
            else:
                self.controller.setFlag(inst_,
                                        InstrumentOperationFlag[status[0].status],
                                        False)


        return

    def check(self, item):

        t0 = time.time()

        self.mustStop.clear()

        if not item.active:
            item.lastUpdate = self.controller.site().ut().replace(tzinfo=None)
            item.status = FlagStatus.UNKNOWN.index
            return

        for check in item.check:

            # aborted?
            if self.mustStop.isSet():
                raise CheckAborted()
            # Should be included in check?

            try:
                self.currentCheck = check
                self.currentHandler = self.checkHandlers[type(check)]

                logMsg = str(self.currentHandler.log(check))
                self.log.debug("[start] %s " % logMsg)
                self.controller.checkBegin(check, logMsg)

                status,msg = self.currentHandler.process(check) # return response id

                self.log.debug("[start] %s: %s " % (status,msg))

                if self.mustStop.isSet():
                    self.controller.checkComplete(check, FlagStatus.ABORTED)
                    raise CheckAborted()
                elif status and (item.eager or status != item.status):
                    self.controller.itemStatusChanged(item,status)
                    # Get response
                    for response in item.response:
                        response_status = ResponseStatus.OK
                        try:
                            self.log.debug('%s' % response.response_id)
                            self.currentResponse = self.responseList[response.response_id]
                            self.controller.itemResponseBegin(item,self.currentResponse)
                            self.currentResponse.process(response)
                        except KeyError:
                            self.log.debug("No handler to response %s. Skipping it" % response.response_id)
                            response_status = ResponseStatus.ERROR
                        except Exception, e:
                            self.log.exception(e)
                            response_status = ResponseStatus.ERROR
                        finally:
                            self.controller.itemResponseComplete(item, self.currentResponse, status)

                    # currentResponse = self.responseList[item.response]
                    #
                    # currentResponse.process(check)

                    # item.status = status.index
                    item.lastChange = self.controller.site().ut().replace(tzinfo=None)
                    self.controller.itemResponseComplete(item,msg)

                self.controller.checkComplete(check, FlagStatus.OK)
                item.lastUpdate = self.controller.site().ut().replace(tzinfo=None)
                item.status = status
            except CheckExecutionException, e:
                self.controller.checkComplete(check, FlagStatus.ERROR)
                raise
            except KeyError:
                self.log.debug("No handler to %s item. Skipping it" % check)
            finally:
                self.log.debug("[finish] took: %f s" % (time.time() - t0))

    def updateInstrumentStatus(self,instrument,status,key=None):
        session = ioSession()
        iostatus = session.query(InstrumentOperationStatus).filter(InstrumentOperationStatus.instrument == instrument)[0]
        session.commit()

        if iostatus.status != InstrumentOperationFlag.LOCK.index:
            iostatus.status = status.index
            if key is not None:
                iostatus.key = key
        elif key == iostatus.key:
            iostatus.status = status.index
            if status != InstrumentOperationFlag.LOCK:
                iostatus.key = ""
        else:
            return False

        session.commit()
        return True

    def getInstrumentStatus(self,instrument):
        session = ioSession()
        iostatus = session.query(InstrumentOperationStatus).filter(InstrumentOperationStatus.instrument == instrument)

        return InstrumentOperationFlag[iostatus[0].status]

    def activate(self,item):
        session = Session()

        activate_item = session.query(List).filter(List.name == item)

        for act in activate_item:
            act = session.merge(act)
            act.active = True

        session.commit()

    def deactivate(self,item):
        session = Session()

        deactivate_item = session.query(List).filter(List.name == item)

        for deact in deactivate_item:
            deact = session.merge(deact)
            deact.active = False

        session.commit()

    def _injectInstrument(self, handler):
        if not (issubclass(handler, CheckHandler) or issubclass(handler, baseresponse.BaseResponse)):
            return

        if issubclass(handler, baseresponse.BaseResponse):
            try:
                setattr(handler, "manager",
                            self.controller.getManager().getProxy(self.controller.getLocation()))
            except Exception, e:
                self.log.error("Could not inject `manager` to %s response"%(handler))
                self.log.exception(e)

        if not hasattr(handler.process, "__requires__"):
            return

        for instrument in handler.process.__requires__:
            try:
                setattr(handler, instrument,
                       self.controller.getManager().getProxy(self.controller[instrument]))
            except ObjectNotFoundException, e:
                self.log.error("No instrument to inject on %s handler" % handler)
            except InvalidLocationException, e:
                self.log.error("No instrument (%s) to inject on %s handler" % (instrument,handler))

