
'''
Implement basic responses to some results on the checklist. The user can implement its own and add it on the fly
as long as they inherit the Response class.
'''

import os, sys
import copy
import subprocess
from chimera_manager.controllers.handlers import requires
from chimera_manager.controllers.status import InstrumentOperationFlag as IOFlag
from chimera_manager.core.exceptions import StatusUpdateException
from chimera_manager.controllers import model
from chimera_manager.controllers.exceptions import DomeActionException, TelescopeActionException

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
    @requires("robobs")
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
            for robobs in StopAll.robobs:
                if robobs is not None:
                    robobs.stop()
        except Exception, e:
            manager.broadCast('Error trying to stop robobs: %s ' % e)
            pass
        else:
            manager.broadCast('Robobs stopped.')

        try:
            for scheduler in StopAll.scheduler:
                scheduler.stop()
        except Exception, e:
            manager.broadCast('Error trying to stop scheduler: %s ' % e)
            pass
        else:
            manager.broadCast('Scheduler stopped.')

        try:
            for telescope in StopAll.telescope:
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
    @requires("site")
    @requires("dome")
    def process(check):

        manager = DomeAction.manager
        site = DomeAction.site
        # dome = DomeAction.dome[0]

        def openFunc(check, open):
            if manager.canOpen("dome"):
                # Try to switch dome flag to operating
                try:
                    manager.setFlag("dome",
                                    IOFlag.OPERATING)
                except StatusUpdateException, e:
                    manager.broadCast(e)
                    raise
                except Exception, e:
                    t, v, tb = sys.exc_info()
                    # If it was not a StatusUpdateException. Try to Switch the status operation to ERROR and
                    try:
                        manager.setFlag("dome",
                                        IOFlag.ERROR)
                    except:
                        raise t, v, tb
                else:
                    # I will only try to open the slit if nothing failed
                    if not check():
                        open()
            else:
                manager.broadCast("Cannot open dome slit due to manager constraints.")
                # Usefull for stopping nested responses
                raise DomeActionException("Cannot open dome slit due to manager constraints.")

        def closeFunc(check,close):
            # Try to switch dome flag to READY
            try:
                cflag = manager.getFlag("dome")
                if cflag == IOFlag.OPERATING:
                    manager.setFlag("dome",
                                    IOFlag.READY)
            except StatusUpdateException, e:
                manager.broadCast(e)
                raise
            except Exception, e:
                t, v, tb = sys.exc_info()
                manager.broadCast(e)
                # If it was not a StatusUpdateException. Try to Switch the status operation to ERROR and
                # raise the exception
                try:
                    manager.setFlag("dome",
                                    IOFlag.ERROR)
                except:
                    raise t, v, tb
            finally:
                # I will try to close the dome regardless of flag switching problems
                try:
                    if check():
                        close()
                except:
                    manager.broadCast("Could not close dome slit!")
                    t, v, tb = sys.exc_info()
                    try:
                        manager.setFlag("dome",
                                        IOFlag.ERROR)
                    except:
                        pass
                    raise t, v, tb

        for dome in DomeAction.dome:
            if check.mode == 0:
                # Open Dome Slit
                manager.broadCast("Opening dome slit...")
                openFunc(dome.isSlitOpen,dome.openSlit)
            elif check.mode == 1:
                # Close dome Slit
                manager.broadCast("Closing dome slit...")
                closeFunc(dome.isSlitOpen,dome.closeSlit)
            elif check.mode == 2:
                # Open dome flap
                manager.broadCast("Opening dome flap...")
                openFunc(dome.isFlapOpen, dome.openFlap)
            elif check.mode == 3:
                # Close dome flap
                # Dome may still be operating with Flap closed. Will close without any flag changes
                if dome.isFlapOpen():
                    try:
                        manager.broadCast("Closing dome flap...")
                        dome.closeFlap()
                    except Exception, e:
                        manager.broadCast(e)
                        raise
            elif check.mode == 4:
                # Move dome either to some standard position or to "parameter" angle
                from chimera.util.coord import Coord
                target = None
                try:
                    if str(check.parameter) == 'oppose-sun':
                        sunpos = site[0].sunpos()
                        sun_long = sunpos.az.D + 180.
                        if sun_long > 360.:
                            sun_long = 360.-sun_long
                        target = Coord.fromD(sun_long)
                    else:
                        target = Coord.fromDMS(str(check.parameter)) # If this fail, action won't be completed
                except Exception, e:
                    manager.broadCast("Could not convert string %s to coordinate. (%s)" % (check.parameter,
                                                                                           repr(e)))
                    return
                else:
                    dome.stand()
                    manager.broadCast("Moving dome to %s ... " % target)
                    dome.slewToAz(target)

            elif check.mode == 5:
                # switch fan on
                try:
                    if ',' in str(check.parameter):
                        fan,speed = str(check.parameter).split(',')
                    else:
                        fan = str(check.parameter)
                        speed = None

                    domefan = dome.getManager().getProxy(fan)

                    if domefan.isSwitchedOn():
                        manager.broadCast("Fan is already running... ")
                    elif domefan.switchOn():
                        manager.broadCast("Dome fan started")
                    else:
                        manager.broadCast("Could not start dome fan")

                    if speed is not None:
                        try:
                            manager.broadCast("Setting fan speed to %s" % speed)
                            domefan.setRotation(float(speed))
                        except Exception, e:
                            manager.broadCast("Could not set dome speed to %s" % speed)

                except Exception, e:
                    manager.broadCast("Could not start dome fan. %s" % repr(e))
                    raise

            elif check.mode == 6:
                # switch fan off
                try:
                    fan = str(check.parameter)

                    domefan = dome.getManager().getProxy(fan)

                    if not domefan.isSwitchedOn():
                        manager.broadCast("Fan is already off... ")
                    elif domefan.switchOff():
                        manager.broadCast("Dome fan stopped")
                    else:
                        manager.broadCast("Could not stop dome fan")
                except Exception, e:
                    manager.broadCast("Could not stop dome fan. %s" % repr(e))
                    raise
            elif check.mode == 7:
                # switch lamp on
                try:
                    domelamp = dome.getManager().getProxy(str(check.parameter))

                    if domelamp.isSwitchedOn():
                        manager.broadCast("Lamp is already on... ")
                    elif domelamp.switchOn():
                        manager.broadCast("Lamp switched on")
                    else:
                        manager.broadCast("Could not switch lamp on")
                except Exception, e:
                    manager.broadCast("Could not switch lamp on. %s" % repr(e))
                    raise
            elif check.mode == 8:
                # switch lamp off
                try:
                    domelamp = dome.getManager().getProxy(str(check.parameter))

                    if not domelamp.isSwitchedOn():
                        manager.broadCast("Lamp is already off... ")
                    elif domelamp.switchOff():
                        manager.broadCast("Lamp switched off")
                    else:
                        manager.broadCast("Could not switch lamp off")
                except Exception, e:
                    manager.broadCast("Could not switch lamp off. %s" % repr(e))
                    raise
            elif check.mode == 9:
                # Switch on Dome track
                from chimera.interfaces.dome import Mode

                manager.broadCast("Activating dome tracking.")
                try:
                    dome.track()
                    if dome.getMode() != Mode.Track:
                        manager.broadCast("Could not set dome tracking.")
                except Exception, e:
                    manager.broadCast("Problem trying to set dome tracking.\n %s" % repr(e))
            elif check.mode == 10:
                # Switch of Dome track
                from chimera.interfaces.dome import Mode

                manager.broadCast("Deactivating dome tracking.")
                try:
                    dome.stand()
                    if dome.getMode() == Mode.Track:
                        manager.broadCast("Could not set dome stand.")
                except Exception, e:
                    manager.broadCast("Problem trying to set dome stand.\n %s" % repr(e))


    @staticmethod
    def model():
        return model.DomeAction

class TelescopeAction(BaseResponse):

    @staticmethod
    @requires("telescope")
    def process(check):
        # tel = TelescopeAction.telescope[0]
        manager = TelescopeAction.manager

        for tel in TelescopeAction.telescope:
            if check.mode == 0:
                try:
                    if manager.getFlag("telescope") != IOFlag.ERROR:
                        manager.broadCast("Unparking telescope...")
                        tel.unpark()
                        manager.setFlag("telescope",IOFlag.READY)
                        manager.setFlag("dome",IOFlag.READY)
                    else:
                        raise TelescopeActionException("Cannot unpark telescope with ERROR flag set. Check instrument.")
                except Exception, e:
                    manager.setFlag("telescope",IOFlag.ERROR)
                    manager.setFlag("dome",IOFlag.CLOSE)

                    manager.broadCast(e)
                    raise
            elif check.mode == 1:
                try:
                    manager.broadCast("Parking telescope...")
                    tel.park()
                    manager.setFlag("telescope",IOFlag.CLOSE)
                    manager.setFlag("dome",IOFlag.CLOSE)
                except Exception, e:
                    manager.setFlag("telescope",IOFlag.ERROR)
                    manager.setFlag("dome",IOFlag.CLOSE)
                    manager.broadCast(e)
                    raise
            elif check.mode == 2:
                if manager.canOpen("telescope"):
                    try:
                        manager.broadCast("Opening Telescope cover.")
                        tel.openCover()
                    except Exception, e:
                        manager.broadCast(e)
                        raise
                else:
                    manager.broadCast("Cannot open telescope cover due to manager constraints.")
                    raise TelescopeActionException("Cannot open telescope cover due to manager constraints.")
            elif check.mode == 3:
                try:
                    manager.broadCast("Closing telescope cover...")
                    tel.closeCover()
                except Exception, e:
                    manager.broadCast(e)
                    raise
            elif check.mode == 5:
                from chimera.util.position import Position
                alt,az = str(check).parameter.split(",")
                target = Position.fromAltAz(alt, az)
                manager.broadCast("Slewing telescope to alt/az %s" % target)
                tel.slewToAltAz(target)
            elif check.mode == 6:
                from chimera.util.position import Position
                ra,dec = check.parameter.split(",")
                target = Position.fromRaDec(ra, dec)
                manager.broadCast("Slewing telescope to ra/dec %s" % target)
                tel.slewToRaDec(target)
            elif check.mode == 7:
                manager.broadCast("Stopping telescope tracking")
                tel.stopTracking()
            elif check.mode == 8:
                # switch fan on
                try:
                    if ',' in str(check.parameter):
                        fan,speed = str(check.parameter).split(',')
                    else:
                        fan = str(check.parameter)
                        speed = None

                    fan = tel.getManager().getProxy(fan)

                    if fan.isSwitchedOn():
                        manager.broadCast("Fan is already running... ")
                    elif fan.switchOn():
                        manager.broadCast("Telescope fan started")
                    else:
                        manager.broadCast("Could not start telescope fan")

                    if speed is not None:
                        try:
                            manager.broadCast("Setting fan speed to %s" % speed)
                            fan.setRotation(float(speed))
                        except Exception, e:
                            manager.broadCast("Could not set telescope speed to %s" % speed)

                except Exception, e:
                    manager.broadCast("Could not start dome fan. %s" % repr(e))
                    raise

            elif check.mode == 9:
                # switch fan off
                try:
                    fan = str(check.parameter)

                    fan = tel.getManager().getProxy(fan)

                    if not fan.isSwitchedOn():
                        manager.broadCast("Fan is already off... ")
                    elif fan.switchOff():
                        manager.broadCast("Telescope fan stopped")
                    else:
                        manager.broadCast("Could not stop telescope fan")
                except Exception, e:
                    manager.broadCast("Could not stop telescope fan. %s" % repr(e))
                    raise
            else:
                manager.broadCast("Not implemented mode %i for telescope" % (check.mode))
                raise TelescopeActionException("Not implemented mode %i for telescope" % (check.mode))

    @staticmethod
    def model():
        return model.TelescopeAction

class DomeFan(BaseResponse):

    @staticmethod
    @requires("dome")
    def process(check):
        dome = DomeFan.dome
        manager = DomeFan.manager

        domefan = dome.getManager().getProxy(str(check.fan))

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
            raise

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
            raise

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
            manager.broadCast('%s' % repr(e))
            pass
        except Exception, e:
            manager.broadCast(e)
            raise


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
        manager = BaseResponse.manager
        if os.path.exists(str(check.filename)):
            manager.broadCast("Running %s " % check.filename)
            ret = subprocess.call(str(check.filename),shell=True)
            # Todo: Check return value and log if different than 0 (execution error)
        else:
            manager.broadCast("Could not find script %s to run... " % check.filename)
        # Todo: Log if there is a problem

    @staticmethod
    def model():
        return model.ExecuteScript

class SendTelegram(BaseResponse):

    @staticmethod
    #@requires("manager")
    def process(check):
        manager = BaseResponse.manager

        manager.broadCast(check.message)

    @staticmethod
    def model():
        return model.SendTelegram

class SendPhoto(BaseResponse):

    @staticmethod
    #@requires("manager")
    def process(check):
        manager = BaseResponse.manager

        if os.path.exists(check.path):
            manager.broadCastPhoto(check.path,check.message)
        else:
            manager.broadCast('Could not find file to send %s\n %s' % (check.path,check.message))

    @staticmethod
    def model():
        return model.SendPhoto

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
    @requires("robobs")
    def process(check):
        # sched = StartScheduler.scheduler
        manager = StartScheduler.manager

        manager.setFlag("scheduler",
                        IOFlag.OPERATING)

        manager.broadCast('Starting scheduler.')
        for sched in StartScheduler.scheduler:
            sched.start()

class StopScheduler(BaseResponse):

    @staticmethod
    @requires("scheduler")
    def process(check):
        # sched = StartScheduler.scheduler
        manager = StartScheduler.manager

        manager.broadCast('Stopping scheduler.')
        for sched in StartScheduler.scheduler:
            sched.stop()

class StartRobObs(BaseResponse):

    @staticmethod
    @requires("robobs")
    def process(check):
        # sched = StartScheduler.scheduler
        manager = StartScheduler.manager

        manager.setFlag("robobs",
                        IOFlag.OPERATING)

        for robobs in StartScheduler.robobs:
            if robobs is not None:
                manager.broadCast('Starting robobs and waking it up.')
                robobs.start()
                robobs.wake()
                return

class StopRobObs(BaseResponse):

    @staticmethod
    @requires("robobs")
    def process(check):
        # sched = StartScheduler.scheduler
        manager = StartScheduler.manager

        manager.setFlag("robobs",
                        IOFlag.READY)

        for robobs in StartScheduler.robobs:
            if robobs is not None:
                manager.broadCast('Stopping robobs.')
                robobs.stop()
                return

class ConfigureScheduler(BaseResponse):
    @staticmethod
    @requires("scheduler")
    def process(check):

        import yaml
        from chimera.util.position import Position
        from chimera.util.coord import Coord
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
        # sched = ConfigureScheduler.scheduler

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
                    raise
                except Exception, e:
                    manager.broadCast('Exception trying to start scheduler: %s' % repr(e))
                    raise

            def _validateOffset(value):
                try:
                    offset = Coord.fromAS(int(value))
                except ValueError:
                    offset = Coord.fromDMS(value)

                return offset

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
                        elif 'name' in actconfig:
                            # self.out('Target name: %s' % actconfig['name'])
                            act.targetName = actconfig['name']
                        elif 'offset' not in actconfig:
                            manager.broadCast('Empty Point action. No target to point to or offset to perform!')
                            continue

                        if 'offset' in actconfig:
                            if 'north' in actconfig['offset']:
                                offset = _validateOffset(actconfig['offset']['north'])
                                act.offsetNS = offset
                            elif 'south' in actconfig['offset']:
                                offset = _validateOffset(actconfig['offset']['south'])
                                act.offsetNS = Coord.fromAS(-offset.AS)

                            if 'west' in actconfig['offset']:
                                offset = _validateOffset(actconfig['offset']['west'])
                                act.offsetEW = offset
                            elif 'east' in actconfig['offset']:
                                offset = _validateOffset(actconfig['offset']['east'])
                                act.offsetEW = Coord.fromAS(-offset.AS)

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
