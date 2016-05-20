
'''
Implement basic responses to some results on the checklist. The user can implement its own and add it on the fly
as long as they inherit the Response class.
'''

import os
import copy
import subprocess
from chimera_manager.controllers.handlers import requires
from chimera_manager.controllers.status import InstrumentOperationFlag as IOFlag
from chimera_manager.core.exceptions import StatusUpdateException
from chimera_manager.controllers import model

class BaseResponse(object):

    @staticmethod
    def process(check):
        pass

    @staticmethod
    def model():
        return model.BaseResponse

class StopAll(BaseResponse):

    @staticmethod
    @requires("telescope")
    @requires("camera")
    @requires("scheduler")
    def process(check):
        manager = StopAll.manager

        try:
            manager.setFlag("scheduler",IOFlag.CLOSE)
        except StatusUpdateException,e:
            manager.broadCast(e)
            pass
        except Exception, e:
            manager.broadCast(e)
            pass

        try:
            scheduler = StopAll.scheduler
            scheduler.stop()
        except Exception, e:
            manager.broadCast(e)
            pass

        try:
            telescope = StopAll.telescope
            # manager.broadCast("Stopping Telescope")
            if telescope.isTracking():
                telescope.stopTracking()
        except NotImplementedError, e:
            pass
        except Exception, e:
            manager.broadCast(e)
            pass

        # try:
        #     manager.setFlag("telescope",IOFlag.CLOSE)
        #     telescope.closeCover()
        # except NotImplementedError, e:
        #     pass
        # except Exception, e:
        #     manager.broadCast(e)
        #     # raise Exception
        #
        # manager.setFlag("dome",IOFlag.CLOSE)
        # dome.stand()
        # dome.close()

        # try:
        #     camera = StopAll.camera
        #     manager.setFlag("camera",IOFlag.CLOSE)
        #
        #     camera.abortExposure(readout=False)
        # except:
        #     pass

class UnparkTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = UnparkTelescope.telescope
        manager = UnparkTelescope.manager

        manager.broadCast("Unpark Telescope")
        try:
            telescope.unpark()
        except Exception, e:
            manager.broadCast(e)

class ParkTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = ParkTelescope.telescope
        manager = ParkTelescope.manager

        try:
            telescope.park()
        except Exception, e:
            manager.broadCast(e)

class OpenTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = OpenTelescope.telescope
        manager = OpenTelescope.manager

        try:
            telescope.openCover()
        except Exception, e:
            manager.broadCast(e)

class CloseTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = OpenTelescope.telescope
        manager = OpenTelescope.manager

        try:
            telescope.closeCover()
        except Exception, e:
            manager.broadCast(e)

class OpenDomeSlit(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = OpenDomeSlit.dome
        manager = OpenDomeSlit.manager

        manager.broadCast("Opening Dome Slit")
        # Check if dome can be opened
        if manager.canOpen("dome"):
            try:
                manager.setFlag("dome",
                                IOFlag.OPERATING)

                # I will only try to open the slit if I can set the flag to operating
                if not dome.isSlitOpen():
                    # manager.broadCast("Opening dome slit")
                    dome.openSlit()

            except StatusUpdateException, e:
                manager.broadCast(e)
            except Exception, e:
                # If it was not a StatusUpdateException. Try to Switch the status operation to ERROR
                # Should I also try to close the slit?
                manager.broadCast(e)
                try:

                    manager.setFlag("dome",
                                    IOFlag.ERROR)

                except:
                    pass

class OpenDomeFlap(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = OpenDomeFlap.dome
        manager = OpenDomeFlap.manager

        # Check if dome can be opened
        if manager.canOpen():
            try:
                manager.setFlag("dome",
                                IOFlag.OPERATING)

                # I will only try to open the flap if I can set the flag to operating
                if not dome.isFlapOpen():
                    dome.openFlap()

            except StatusUpdateException, e:
                manager.broadCast(e)
            except:
                # If it was not a StatusUpdateException. Try to Switch the status operation to ERROR
                try:
                    manager.setFlag("dome",
                                    IOFlag.ERROR)
                except:
                    pass

class CloseDomeSlit(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = CloseDomeSlit.dome
        manager = CloseDomeSlit.manager

        try:
            manager.setFlag("dome",
                            IOFlag.READY)
        except StatusUpdateException, e:
            manager.broadCast(e)
        except Exception, e:
            manager.broadCast(e)

        # I will try to close the dome regardless of flag switching problems
        if dome.isSlitOpen():
            dome.closeSlit()

class CloseDomeFlap(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = CloseDomeFlap.dome
        manager = CloseDomeFlap.manager

        # Dome may still be operating with Flap closed. Will close without any flap changes
        if dome.isFlapOpen():
            try:
                dome.closeFlap()
            except Exception, e:
                manager.broadCast(e)

class DomeFan(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = DomeFan.dome
        manager = DomeFan.manager

        manager.broadCast('%s' % check.fan)
        domefan = dome.getManager().getProxy(check.fan)

        if domefan.isSwitchedOn():
            manager.broadCast("Fan is already running... ")

        try:
            if check.mode == 0:
                if domefan.switchOn():
                    manager.broadCast("Dome fan started")
                else:
                    manager.broadCast("Could not start dome fan")
            elif check.mode == 1:
                if domefan.switchOff():
                    manager.broadCast("Dome fan stopped")
                else:
                    manager.broadCast("Could not stop dome fan")

        except Exception, e:
            manager.broadCast("Could not start dome fan. %s" % repr(e))

    @staticmethod
    def model():
        return model.DomeFan

        # Check if domefan can be opened
        # if manager.getFlag("domefan") == IOFlag.OPEN:
        #     # Switch flag to OPERATING
        #     manager.setFlag("domefan",IOFlag.OPERATING)
        #     if not domefan.isFanRunning():
        #         domefan.startFan()

class LockInstrument(BaseResponse):
    @staticmethod
    def process(check):
        manager = LockInstrument.manager

        manager.broadCast('Locking %s with key %s' % (check.instrument,
                                                      check.key))
        try:
            manager.lockInstrument(check.instrument,
                                   check.key)
        except Exception,e:
            manager.broadCast(e)

    @staticmethod
    def model():
        return model.LockInstrument


class UnlockInstrument(BaseResponse):
    @staticmethod
    def process(check):
        manager = UnlockInstrument.manager

        try:
            success = manager.unlockInstrument(check.instrument,
                                               check.key)
            if success:
                manager.broadCast('%s unlocked with key %s' % (check.instrument,
                                                                check.key))
        except StatusUpdateException, e:
            pass
        except Exception, e:
            manager.broadCast(e)


    @staticmethod
    def model():
        return model.UnlockInstrument

class SetInstrumentFlag(BaseResponse):
    @staticmethod
    def process(check):
        manager = SetInstrumentFlag.manager

        manager.setFlag(check.instrument,
                        check.flag)
    @staticmethod
    def model():
        return model.SetInstrumentFlag

class ExecuteScript(BaseResponse):

    @staticmethod
    def process(check):
        if os.path.exists(check.script):
            ret = subprocess.call([check.script])
            # Todo: Check return value and log if different than 0 (execution error)
        # Todo: Log if there is a problem

class SendTelegram(BaseResponse):

    @staticmethod
    #@requires("manager")
    def process(check):
        manager = BaseResponse.manager

        manager.broadCast(check.message)

    @staticmethod
    def model():
        return model.SendTelegram

class Question(BaseResponse):
    @staticmethod
    def process(check):
        manager = BaseResponse.manager
        result = manager.askWatcher(check.question,check.waittime)
        manager.broadCast(result)

    @staticmethod
    def model():
        return model.Question

class ActivateItem(BaseResponse):
    @staticmethod
    def process(check):
        manager = BaseResponse.manager
        manager = copy.copy(manager)

        manager.broadCast("Activating item %s " % check.item)
        manager.activate(check.item)

    @staticmethod
    def model():
        return model.ActivateItem

class DeactivateItem(BaseResponse):
    @staticmethod
    def process(check):
        manager = BaseResponse.manager
        manager = copy.copy(manager)

        manager.broadCast("Deactivating item %s " % check.item)
        manager.deactivate(check.item)

    @staticmethod
    def model():
        return model.DeactivateItem
