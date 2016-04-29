
from chimera_manager.controllers.model import (Session, List, CheckTime, CheckHumidity,
                                               CheckTemperature, CheckWindSpeed,
                                               CheckDewPoint, CheckDew, AskListener,
                                               CheckDome, CheckTransparency, CheckInstrumentFlag,
                                               Response)
from chimera_manager.controllers.iostatus_model import Session as ioSession
from chimera_manager.controllers.iostatus_model import InstrumentOperationStatus

from chimera_manager.controllers.handlers import (CheckHandler, TimeHandler,
                                                  HumidityHandler, TemperatureHandler, TransparencyHandler,
                                                  WindSpeedHandler, DewPointHandler, InstrumentFlagHandler,
                                                  DewHandler, AskListenerHandler,
                                                  DomeHandler)
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
                              AskListener:      AskListenerHandler,
                              CheckDome: DomeHandler,
                              CheckTransparency: TransparencyHandler,
                              CheckInstrumentFlag: InstrumentFlagHandler,
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

        status = False
        run_status = False
        msg = ''
        for check in item.check:

            # aborted?
            if self.mustStop.isSet():
                raise CheckAborted()
            # Should be included in check?

            try:
                self.currentCheck = check
                try:
                    self.currentHandler = self.checkHandlers[type(check)]
                except KeyError:
                    self.log.error("No handler to %s item. Skipping it" % check)
                    continue

                logMsg = str(self.currentHandler.log(check))
                self.log.debug("[start] %s " % logMsg)
                self.controller.checkBegin(check, logMsg)

                i_status,i_msg = self.currentHandler.process(check) # return response id
                # self.log.debug("%s and (%s or (%s != %s)) = %s" % (i_status,
                #                                                    item.eager,
                #                                                    i_status,
                #                                                    item.status))
                status = i_status
                run_status = i_status and (item.eager or (i_status != item.status))
                msg += i_msg

                if self.mustStop.isSet():
                    self.controller.checkComplete(check, FlagStatus.ABORTED)
                    raise CheckAborted()
                elif not status:
                    break

            except CheckExecutionException, e:
                self.controller.checkComplete(check, FlagStatus.ERROR)
                raise
            except Exception, e:
                self.log.debug("Exception in check routine: %s" % repr(e))
                self.controller.checkComplete(check, FlagStatus.ERROR)
                status = False
                break
            else:
                self.controller.checkComplete(check, FlagStatus.OK)

        self.log.debug("[start] %s: %s " % (status,msg))

        if run_status:

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

        item.lastUpdate = self.controller.site().ut().replace(tzinfo=None)
        item.status = status

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

    def instrumentKey(self,instrument):
        session = ioSession()
        iostatus = session.query(InstrumentOperationStatus).filter(InstrumentOperationStatus.instrument == instrument)

        return iostatus[0].key

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

        if issubclass(handler, CheckHandler):
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
                if instrument == "weatherstations":
                    ws_list = []
                    for i, ws in enumerate(self.controller[instrument]):
                        try:
                            ws_manager = self.controller.getManager().getProxy(ws)
                            ws_list.append(ws_manager)
                        except Exception, e:
                            self.log.error('Could not inject weather station %s on %s handler' % (ws,
                                                                                                  handler))
                            self.log.exception(e)
                    if len(ws_list) > 0:
                        setattr(handler, instrument, ws_list)
                else:
                    setattr(handler, instrument,
                            self.controller.getManager().getProxy(self.controller[instrument]))
            except ObjectNotFoundException, e:
                self.log.error("No instrument to inject on %s handler" % handler)
            except InvalidLocationException, e:
                self.log.error("No instrument (%s) to inject on %s handler" % (instrument,handler))

