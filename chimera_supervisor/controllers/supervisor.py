
import os
import shutil
import contextlib
import urllib

from chimera_supervisor.controllers.machine import Machine
from chimera_supervisor.controllers.checklist import CheckList
from chimera_supervisor.controllers.status import OperationStatus, InstrumentOperationFlag
from chimera_supervisor.controllers.states import State
from chimera_supervisor.core.exceptions import StatusUpdateException

from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.chimeraobject import ChimeraObject
from chimera.core.lock import lock
from chimera.core.event import event
from chimera.core.log import fmt
from chimera.controllers.scheduler.states import State as SchedState
from chimera.controllers.scheduler.status import SchedulerStatus as SchedStatus
from chimera.interfaces.telescope import TelescopeStatus

import threading
import telnetlib
import telegram
import telegram.ext
import logging
import logging.handlers
import time
from collections import OrderedDict

class Supervisor(ChimeraObject):

    __config__ = {  "site"       : "/Site/0",
                    "telescope"  : "/Telescope/0",
                    "camera"     : "/Camera/0",
                    "dome"       : "/Dome/0",
                    "scheduler"  : None,
                    "robobs"     : None,
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


        self._base_instrument_list = ["site", "telescope", "camera", "dome", "scheduler", "robobs",
                                      "domefan", "weatherstations"]
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

        # every day backup supervisor log file and start over
        timestr = time.strftime("%Y%m%d")
        if timestr != self._loggertime:
            self._openLogger()


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
            self.updater = telegram.ext.Updater(bot=self.bot)

            # self.updater.dispatcher.addHandler(CommandHandler('start', start))
            # self.updater.dispatcher.addHandler(CallbackQueryHandler(button))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('list', self.telegramList))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('run', self.telegramRun))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('info', self.telegramInfo))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('lock', self.telegramLock))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('unlock', self.telegramUnLock))
            self.updater.dispatcher.add_handler(telegram.ext.CommandHandler('help', self.telegramHelp))
            # self.updater.dispatcher.addErrorHandler(error)

            # def start_telegram_polling():
            #     self.updater.start_polling()
            #
            #     # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
            #     # SIGTERM or SIGABRT
            #     # self.updater.idle()
            #
            # self._telegramPollingThread = threading.Thread(target=start_telegram_polling)
            # self._telegramPollingThread.setDaemon(True)
            # self._telegramPollingThread.start()
            self.updater.start_polling()

    def disconnectTelegram(self):
        self.updater.stop()

    def telegramList(self, bot, update):
        # bot.sendMessage(update.message.chat_id, text="Retrieving action list.")
        items = self.checklist.getInactive()
        if len(items) == 0:
            bot.sendMessage(update.message.chat_id, text="No action available")
            return

        msg = 'Select an item to run:\n'
        keyboard = []
        for item in items:
            keyboard.append([telegram.InlineKeyboardButton('%s' % item, callback_data='%s' % item)])

        reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        updates = self.bot.getUpdates()
        update_id=None
        for update in updates:
            update_id = updates[-1].update_id + 1

        # bot.sendMessage(update.message.chat_id, text=msg)
        msg_id = bot.sendMessage(chat_id=update.message.chat_id,
                                 text=msg,
                                 reply_markup=reply_markup
                                 )

        start_time = time.time()
        while time.time() - start_time < 60:

            updates = self.bot.getUpdates(offset = update_id)

            for new_update in updates:
                try:
                    query = new_update.callback_query
                    if query is None:
                        continue
                    dd = new_update.to_dict()

                    answer = query.data
                    if answer in items:
                        self.bot.editMessageText(text='Running action %s...' % answer,
                                            chat_id=msg_id.chat_id,
                                            message_id=msg_id.message_id)
                        self.machine.runAction(answer)
                        return
                    else:
                        self.bot.editMessageText(text='Unidentified answer %s... Try again...' % answer,
                                            chat_id=msg_id.chat_id,
                                            message_id=msg_id.message_id)


                except Exception, e:
                    self.log.exception(e)

        self.bot.editMessageText(text='Timed out...',
                            chat_id=msg_id.chat_id,
                            message_id=msg_id.message_id)


    def telegramRun(self, bot, update):
        # bot.sendMessage(update.message.chat_id, text="Running action \"%s\"." % update.message.text)
        items = self.checklist.getInactive()
        action = str(update.message.text).split(" ")[1]
        if action in items:
            bot.sendMessage(update.message.chat_id, text="Running action \"%s\"." % action)
            self.machine.runAction(action)
        else:
            bot.sendMessage(update.message.chat_id, text="Action \"%s\" not available." % action)

    def telegramInfo(self, bot, update):
        # bot.sendMessage(update.message.chat_id, text="Retrieving manager info.")
        msg = "General status:\n"

        for inst_ in self.getInstrumentList():
            flag = self.getFlag(inst_)
            key = ""
            if self.getFlag(inst_) == InstrumentOperationFlag.LOCK:
                key = ' %s' % self.getInstrumentKey(inst_)

            msg += "- %s: %s %s\n"%(inst_,
                                    flag,
                                    key)
        bot.sendMessage(update.message.chat_id, text=msg)

    def telegramLock(self, bot, update):
        try:
            instrument, key = str(update.message.text).split(" ")[1:3]
        except:
            bot.sendMessage(update.message.chat_id, text="Could not parse input string \"%s\"." % update.message.text)
            return

        try:
            self.lockInstrument(instrument,key)
        except:
            bot.sendMessage(update.message.chat_id, text="Could not lock %s with key %s." % (instrument,
                                                                                             key))
        else:
            bot.sendMessage(update.message.chat_id, text="%s locked with key %s." % (instrument,
                                                                                             key))

    def telegramUnLock(self, bot, update):
        try:
            instrument, key = str(update.message.text).split(" ")[1:3]
        except:
            bot.sendMessage(update.message.chat_id, text="Could not parse input string \"%s\"." % update.message.text)
            return

        instrument_key_list = self.getInstrumentKey(instrument)
        if key in instrument_key_list:
            try:
                self.unlockInstrument(instrument,key)
            except:
                if key not in self.getInstrumentKey(instrument):
                    bot.sendMessage(update.message.chat_id, text="%s unlocked with key %s." % (instrument,
                                                                                               key))
                else:
                    bot.sendMessage(update.message.chat_id, text="Could not unlock %s with key %s." % (instrument,
                                                                                                       key))
            else:
                    bot.sendMessage(update.message.chat_id, text="%s unlocked with key %s." % (instrument,
                                                                                               key))
        else:
            bot.sendMessage(update.message.chat_id, text="%s not locked with key %s." % (instrument,
                                                                           key))

    def telegramHelp(self, bot, update):
        helpMSG = '''Commands:
/list - List current available actions.
/run [action] - Run specific action from command list.
/info - Get current manager state.
/lock [instrument] [key] - lock instrument with specified key
/unlock [instrument] [key] - unlock instrument with specified key (use with care!)
/help - Show this help page.
        '''
        bot.sendMessage(update.message.chat_id, text=helpMSG)

    def isTelegramConnected(self):
        return self.bot is not None

    def _openLogger(self):

        self._loggertime = time.strftime("%Y%m%d")

        if self._log_handler:
            self._closeLogger()

        logfile = os.path.join(SYSTEM_CONFIG_DIRECTORY,
                               "supervisor.log")

        if os.path.exists(logfile):
            shutil.move(logfile, os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                              "supervisor_%s.log"%time.strftime("%Y%m%d-%H%M%S")))

        self._log_handler = logging.FileHandler(logfile)

        # self._log_handler.setFormatter(logging.Formatter(fmt='%(asctime)s.%(msecs)d %(origin)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s'))
        self._log_handler.setFormatter(logging.Formatter(fmt='%(asctime)s[%(levelname)8s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
        self._log_handler.setLevel(logging.DEBUG)
        self.log.addHandler(self._log_handler)

        self.debuglog = logging.getLogger('supervisor-debug')

        fileHandler = logging.handlers.RotatingFileHandler(os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                              "supervisor-debug.log"),
                                                               maxBytes=100 *
                                                               1024 * 1024,
                                                               backupCount=10)

        # _log_handler = logging.FileHandler(fileHandler)
        fileHandler.setFormatter(logging.Formatter(fmt='%(asctime)s[%(levelname)s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
        # _log_handler.setLevel(logging.DEBUG)
        self.debuglog.addHandler(fileHandler)
        self.debuglog.setLevel(logging.DEBUG)
        # self.log.setLevel(logging.INFO)

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

    def broadCastPhoto(self,path,msg=''):
        if self.bot is not None and self["telegram-broascast-ids"] is not None:
            self.log.debug('Sending %s to %i listeners' % (path, len(self._broadcast_ids)))
            try:
                for id in self._broadcast_ids:
                    with contextlib.closing(urllib.urlopen(str(path))) as fp:
                        self.bot.sendPhoto(chat_id=id, photo=fp.fp)
            except Exception, e:
                self.log.exception(e)
        else:
            self.log.error('No one to send image to!')

    def askWatcher(self,question,waittime):

        if self.bot is not None and self["telegram-listen-ids"] is not None:

            updates = self.bot.getUpdates()
            update_id=None
            for update in updates:
                update_id = updates[-1].update_id + 1

            keyboard = [[telegram.InlineKeyboardButton("Yes", callback_data='OK'),
                         telegram.InlineKeyboardButton("No", callback_data='NO'),
                         telegram.InlineKeyboardButton("Lock dome!", callback_data='lock')]]

            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

            # bot.sendMessage(update.message.chat_id, text="Please choose:", reply_markup=reply_markup)

            self.log.debug('Asking lister %s.' % question)

            msg_ids = []
            for id in self._listen_ids:
                msg_ids.append(self.bot.sendMessage(chat_id=id,
                                     text='[waittime: %i s] %s' %
                                          (waittime,
                                           question),
                                     reply_markup=reply_markup
                                     ))

            start_time = time.time()
            while time.time() - start_time < waittime:

                updates = self.bot.getUpdates(offset = update_id)

                for update in updates:
                    try:
                        query = update.callback_query
                        if query is None:
                            continue
                        dd = update.to_dict()
                        # print dd
                        # self.bot.editMessageText(text="Selected option: %s by %s" % (query.data,
                        #                                                              dd['callback_query']['message']['chat']['username']),
                        #                          chat_id=query.message.chat_id,
                        #                          message_id=query.message.message_id)

                        if query.message.chat_id in self._listen_ids:
                            for msg in msg_ids:
                                self.bot.editMessageText(text="%s \n Selected option: %s by %s" % (
                                    dd['callback_query']['message']['text'],
                                                    query.data,
                                                    dd['callback_query']['message']['chat']['username']),
                                                    chat_id=msg.chat_id,
                                                    message_id=msg.message_id)
                            answer = query.data
                            if answer is not None:
                                return answer
                            else:
                                return 'No'
                        # else:
                        #     for msg in msg_ids:
                        #         self.bot.editMessageText(text="Selected option: %s by %s" % (query.data,
                        #                             dd['callback_query']['message']['chat']['username']),
                        #                             chat_id=msg.message.chat_id,
                        #                             message_id=msg.message.message_id)
                    except Exception,e:
                        self.log.exception(e)
                    update_id = update.update_id+1


            for ids in msg_ids:
                self.bot.editMessageText(text="%s (Timed out)" % ids.text,
                                         chat_id=ids.chat_id,
                                         message_id=ids.message_id)

            return 'No'

    def site(self):
        return self.getManager().getProxy('/Site/0')

    def getInstrumentLocationList(self, instrument):
        return self._instrument_list[instrument]

    def getTel(self,index=0):
        return self.getManager().getProxy(self._instrument_list["telescope"][index])

    def getSched(self,index=0):
        return self.getManager().getProxy(self._instrument_list["scheduler"][index])

    def getRobObs(self,index=0):
        return self.getManager().getProxy(self["robobs"][index])

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
            return ((self.getFlag(instrument) == InstrumentOperationFlag.READY) or
                   (self.getFlag(instrument) == InstrumentOperationFlag.OPERATING))and \
                   ((self.getFlag("site") == InstrumentOperationFlag.READY) or
                    (self.getFlag("site") == InstrumentOperationFlag.OPERATING))


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

    def hasKey(self,instrument,key):

        if self.getFlag(instrument) != InstrumentOperationFlag.LOCK:
            self.log.debug("Instrument not locked")
            return False

        return key in self.checklist.instrumentKey(instrument)

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
        self.broadCast('Telescope tracking stopped with status %s.' % status)
        if status == TelescopeStatus.OBJECT_TOO_LOW:
            # Todo: Make this an action on the checklist database, so user can configure what to do
            robobs = self.getRobObs()
            sched = self.getSched()
            robobs.stop()
            sched.stop()
            tel = self.getTel()
            from chimera.util.position import Position
            from chimera.util.coord import Coord
            park_position = Position.fromAltAz(Coord.fromD(80),Coord.fromD(89))
            tel.slewToAltAz(park_position)
            robobs.reset_scheduler()
            robobs.start()
            robobs.wake()


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
            if not self.runAction('SchedulerInError'):
                self.broadCast("Could not run action in response to a scheduler error.")

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
