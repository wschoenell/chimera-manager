
'''
Implement basic responses to some results on the checklist. The user can implement its own and add it on the fly
as long as they inherit the Response class.
'''

import os
import subprocess
from chimera_manager.controllers.handlers import requires

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
        scheduler = StopAll.scheduler
        telescope = StopAll.telescope
        dome = StopAll.dome
        camera = StopAll.camera

        try:
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
            telescope.closeCover()
        except NotImplementedError, e:
            pass
        except Exception, e:
            # Todo: Log this exception somehow. I can't stop here. I need to make sure I try to close everything
            pass
            # raise Exception

        dome.stand()
        dome.close()

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

        dome.openSlit()

class CloseDome(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = CloseDome.dome

        dome.closeSlit()

class StartDomeFan(BaseResponse):

    @staticmethod
    @requires("domefan")
    def process(check):
        domefan = StartDomeFan.domefan

        domefan.startFan()

class StopDomeFan(BaseResponse):

    @staticmethod
    @requires("domefan")
    def process(check):
        domefan = StartDomeFan.domefan

        domefan.stopFan()

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
