
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

class DomeAction(BaseResponse):
    '''
    Perform Dome actions.
    0 - Open dome slit
    1 - Close dome slit
    2 - Open dome flap
    3 - Close dome flap
    4 - Rotate dome to "parameter" angle
    '''

    @staticmethod
    @requires("dome")
    def process(check):
        dome = DomeAction.dome
        manager = DomeAction.manager

        if check.mode == 0:
            # Open Dome Slit
            # Check if dome can be opened
            if manager.canOpen():
                try:
                    manager.setFlag("dome",
                                    IOFlag.OPERATING)

                    # I will only try to open the flap if I can set the flag to operating
                    if not dome.isSlitOpen():
                        dome.openSlit()

                except StatusUpdateException, e:
                    manager.broadCast(e)
                except:
                    # If it was not a StatusUpdateException. Try to Switch the status operation to ERROR
                    try:
                        manager.setFlag("dome",
                                        IOFlag.ERROR)
                    except:
                        pass
        elif check.mode == 1:
            # Close dome Slit
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
        elif check.mode == 2:
            # Open dome flap
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
        elif check.mode == 3:
            # Close dome flap
            # Dome may still be operating with Flap closed. Will close without any flag changes
            if dome.isFlapOpen():
                try:
                    dome.closeFlap()
                except Exception, e:
                    manager.broadCast(e)
        elif check.mode == 4:
            # Move dome to "parameter" angle
            from chimera.util.coord import Coord
            target = Coord.fromDMS(check.parameter) # If this fail, action won't be completed
            dome.stand()
            manager.broadCast("Moving dome to %s ... " % target)
            dome.slewToAz(target)

    @staticmethod
    def model():
        return model.DomeAction

class TelescopeAction(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        tel = TelescopeAction.telescope
        manager = TelescopeAction.manager

        if check.mode == 0:
            try:
                tel.unpark()
            except Exception, e:
                manager.broadCast(e)
        if check.mode == 1:
            try:
                tel.park()
            except Exception, e:
                manager.broadCast(e)
        if check.mode == 2:
            try:
                tel.openCover()
            except Exception, e:
                manager.broadCast(e)
        if check.mode == 3:
            try:
                tel.closeCover()
            except Exception, e:
                manager.broadCast(e)
    @staticmethod
    def model():
        return model.TelescopeAction

class DomeFan(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = DomeFan.dome
        manager = DomeFan.manager

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
                        IOFlag[check.flag])
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

class StartScheduler(BaseResponse):

    @staticmethod
    @requires("scheduler")
    def process(check):
        sched = StartScheduler.scheduler
        manager = BaseResponse.manager

        manager.setFlag("scheduler",
                        IOFlag.OPERATING)

        sched.start()


class ConfigureScheduler(BaseResponse):
    @staticmethod
    @requires("scheduler")
    def process(check):

        import yaml
        from chimera.util.position import Position
        from chimera.controllers.scheduler.model import (Session, Program, AutoFocus, AutoFlat,
                                                 PointVerify, Point,
                                                 Expose)

        actionDict = {'autofocus' : AutoFocus,
                      'autoflat'  : AutoFlat,
                      'pointverify' : PointVerify,
                      'point' : Point,
                      'expose' : Expose,
              }

        manager = BaseResponse.manager
        sched = ConfigureScheduler.scheduler

        # delete all programs
        session = Session()
        programs = session.query(Program).all()
        for program in programs:
            session.delete(program)
        session.commit()

        def generateDatabase(options):

            with open(os.path.join(os.path.expanduser('~/'),
                    options.filename), 'r') as stream:
                try:
                    prgconfig = yaml.load(stream)
                except yaml.YAMLError as exc:

                    manager.broadCast(exc)
                    return -1

            session = Session()

            programs = []

            for prg in prgconfig['programs']:

                # process program

                program = Program()
                for key in prg.keys():
                    if hasattr(program,key) and key != 'actions':
                        try:
                            setattr(program,key,prg[key])
                        except:
                            manager.broadCast('Could not set attribute %s = %s on Program' % (key,prg[key]))

                # self.out("# program: %s" % program.name)

                # process actions
                for actconfig in prg['actions']:
                    act = actionDict[actconfig['action']]()
                    # self.out('Action: %s' % actconfig['action'])

                    if actconfig['action'] == 'point':
                        if 'ra' in actconfig.keys() and 'dec' in actconfig.keys():
                            epoch = 'J2000' if 'epoch' not in actconfig.keys() else actconfig['epoch']
                            position = Position.fromRaDec(actconfig['ra'], actconfig['dec'], epoch)
                            # self.out('Coords: %s' % position)
                            act.targetRaDec = position
                            # act = Point(targetRaDec=position)
                        elif 'alt' in actconfig.keys() and 'az' in actconfig.keys():
                            position = Position.fromAltAz(actconfig['alt'], actconfig['az'])
                            # self.out('Coords: %s' % position)
                            act.targetAltAz = position
                        else:
                            # self.out('Target name: %s' % actconfig['name'])
                            act.targetName = actconfig['name']

                    else:
                        for key in actconfig.keys():
                            if hasattr(act,key) and key != 'action':
                                # self.out('\t%s: %s' % (key,actconfig[key]))
                                try:
                                    setattr(act,key,actconfig[key])
                                except:
                                    manager.broadCast('Could not set attribute %s = %s on action %s' % (key,
                                                                                               actconfig[key],
                                                                                               actconfig['action']))
                    program.actions.append(act)

                # self.out("")
                programs.append(program)

            # self.out("List contain %i programs" % len(programs))
            session.add_all(programs)
            session.commit()

            return 0
            # self.out("Restart the scheduler to run it with the new database.")

        if generateDatabase(check) < 0:
            manager.broadCast("Could not configure scheduler with provided arguments.")
            manager.setFlag("scheduler",
                            IOFlag.ERROR)
        else:
            manager.setFlag("scheduler",
                            IOFlag.READY)
            manager.broadCast("Scheduler configured. Restart it to run with the new database.")

    @staticmethod
    def model():
        return model.ConfigureScheduler
