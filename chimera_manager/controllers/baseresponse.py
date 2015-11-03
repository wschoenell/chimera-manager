
'''
Implement basic responses to some results on the checklist. The user can implement its own and add it on the fly
as long as they inherit the Response class.
'''

import os
import subprocess
from chimera_manager.controllers.handlers import requires
from chimera_manager.controllers.status import InstrumentOperationFlag as IOFlag

class BaseResponse(object):

    @staticmethod
    def process(check):
        pass

class StopAll(BaseResponse):

    @staticmethod
    @requires("dome")
    @requires("telescope")
    @requires("camera")
    @requires("scheduler")
    def process(check):
        manager = StopAll.manager
        scheduler = StopAll.scheduler
        telescope = StopAll.telescope
        dome = StopAll.dome
        camera = StopAll.camera

        try:
            manager.setFlag("scheduler",IOFlag.CLOSE)
            scheduler.stop()
        except Exception, e:
                # Todo: Log this exception somehow. I can't stop here. I need to make sure I try to close everything
                pass

        if telescope.isTracking():
            try:
                telescope.stopTracking()
            except NotImplementedError, e:
                pass
            except Exception, e:
                # Todo: Log this exception somehow. I can't stop here. I need to make sure I try to close everything
                pass
                # raise Exception

        try:
            manager.setFlag("telescope",IOFlag.CLOSE)
            telescope.closeCover()
        except NotImplementedError, e:
            pass
        except Exception, e:
            # Todo: Log this exception somehow. I can't stop here. I need to make sure I try to close everything
            pass
            # raise Exception

        manager.setFlag("dome",IOFlag.CLOSE)
        dome.stand()
        dome.close()

        manager.setFlag("camera",IOFlag.CLOSE)
        camera.abortExposure(readout=False)

class UnparkTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = UnparkTelescope.telescope

        telescope.unpark()

class ParkTelescope(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = ParkTelescope.telescope

        telescope.park()

class OpenDome(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = OpenDome.dome
        manager = OpenDome.manager

        # Check if dome can be opened
        if manager.canOpen():
            dome.openSlit()

class CloseDome(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = CloseDome.dome
        # manager = CloseDome.manager

        # manager.setFlag("dome",IOFlag.CLOSE)
        dome.closeSlit()

class StartDomeFan(BaseResponse):

    @staticmethod
    @requires("domefan")
    def process(check):
        domefan = StartDomeFan.domefan
        manager = OpenDome.manager

        # Check if domefan can be opened
        if manager.getFlag("domefan") == IOFlag.OPEN:
            domefan.startFan()

class StopDomeFan(BaseResponse):

    @staticmethod
    @requires("domefan")
    def process(check):
        domefan = StartDomeFan.domefan

        domefan.stopFan()

class LockInstrument(BaseResponse):
    @staticmethod
    def process(check):
        manager = LockInstrument.manager

        manager.lockInstrument(check.instrument,
                               check.key)

class UnlockInstrument(BaseResponse):
    @staticmethod
    def process(check):
        manager = UnlockInstrument.manager

        manager.unlockInstrument(check.instrument,
                                 check.key)

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
