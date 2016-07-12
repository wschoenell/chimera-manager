import datetime

def requires(instrument):
    """Simple dependecy injection mechanism. See ProgramExecutor"""

    def requires_deco(func):
        if hasattr(func, "__requires__"):
            func.__requires__.append(instrument)
        else:
            func.__requires__ = [instrument]
        return func

    return requires_deco

class CheckHandler(object):

    @staticmethod
    def process(check):
        pass

    @staticmethod
    def abort(check):
        pass

    @staticmethod
    def log(check):
        return str(check)

class TimeHandler(CheckHandler):
    '''
    This class checks if now is before of after a specified time delta with respect to a specific sun event.

    Available modes are
    0 - Sun set (sun setting @ alt 0)
    1 - Same as 0, but enable to choose before or after.
    2 - Sun set twilight begin (sun setting @ alt -12)
    3 - Sun set twilight end (sun setting @ alt -18)
    4 - Sun rise (sun rising @ alt 0)
    5 - Sun rise twilight begin (sun setting @ alt -12)
    6 - Sun rise twilight end (sun setting @ alt -18)
   >6 - Specify a reference time (in hours from ut = 0)

    Process
    will return True if the
    sun is above the specified value or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    def process(check):
        site = TimeHandler.site[0]

        ut = site.ut()
        reftime = None
        if abs(check.mode) == 1 or check.mode == 0:
            reftime = site.sunset()
        elif abs(check.mode) == 2:
            reftime = site.sunset_twilight_begin()
        elif abs(check.mode) == 3:
            reftime = site.sunset_twilight_end()
        elif abs(check.mode) == 4:
            reftime = site.sunrise()
        elif abs(check.mode) == 5:
            reftime = site.sunrise_twilight_begin()
        elif abs(check.mode) == 6:
            reftime = site.sunrise_twilight_end()
        else:
            reftime = check.time

        if reftime is None:
            return False,"Could not determined reference time."
        elif check.mode >= 0:
            reftime += check.deltaTime
            ret = ut.time() > reftime.time()
            msg = "Reference time (%s) has passed. Now %s"%(reftime,ut) if ret else \
                "Reference time (%s) still in the future. Now %s"%(reftime,ut)
            return ret,msg
        else:
            reftime += check.deltaTime
            # ut = site.ut()
            ret = ut.time() < reftime.time()
            msg = "Reference time (%s) still in the future. Now %s"%(reftime,ut) if ret else \
                "Reference time (%s) has passed. Now %s"%(reftime,ut)
            return ret,msg

    @staticmethod
    def log(check):
        return "%s"%(check)


class HumidityHandler(CheckHandler):
    '''
    This class checks if humidity is above or bellow some threshold.

    Process will return True if humidity is above specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    @requires("weatherstations")
    def process(check):

        weatherstations = HumidityHandler.weatherstations
        site = HumidityHandler.site[0]

        manager = HumidityHandler.manager

        humidity = None
        for i in range(len(weatherstations)):
            h = weatherstations[i].humidity()
            if datetime.datetime.utcnow() - h.time < datetime.timedelta(minutes=manager["max_mins"]):
                humidity = h
                break
        if humidity is None:
            return check.mode == 0, "No valid weather station data available!"

        if check.mode == 0: # True if value is higher
            ret = check.humidity < humidity.value
            msg = "Humidity OK (%.2f/%.2f)"%(humidity.value,check.humidity) if not ret \
                else "Humidity higher than specified threshold (%.2f/%.2f)"%(humidity.value,check.humidity)
            if ret:
                check.time = site.ut().replace(tzinfo=None)
            return ret, msg
        elif check.mode == 1: # True if value is lower for more than the specified number of hours
            ret = check.humidity > humidity.value
            msg = "Nothing to do. Humidity higher than threshold (%.2f/%.2f)."%(humidity.value,check.humidity) if not ret \
                else "Humidity lower than threshold (%.2f/%.2f)."%(humidity.value,check.humidity)

            if not ret:
                check.time = site.ut().replace(tzinfo=None)
            elif check.time is not None:
                ret = check.time + datetime.timedelta(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
                if ret:
                    msg += "Elapsed time ok"
                    check.time = site.ut().replace(tzinfo=None)
                else:
                    msg += "Elapsed time () too short."
            else:
                check.time = site.ut().replace(tzinfo=None)
                ret = False

            return ret,msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class TemperatureHandler(CheckHandler):
    '''
    This class checks if temperature is above or bellow some threshold.

    Process will return True if temperature is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    @requires("weatherstations")
    def process(check):
        weatherstations = TemperatureHandler.weatherstations
        site = TemperatureHandler.site[0]

        manager = TemperatureHandler.manager

        temperature = None
        for i in range(len(weatherstations)):
            t = weatherstations[i].temperature()
            if datetime.datetime.utcnow() - t.time < datetime.timedelta(minutes=manager["max_mins"]):
                humidity = t
                break
        if temperature is None:
            return check.mode == 0, "No valid weather station data available!"

        if check.mode == 0:
            ret = check.temperature > temperature.value
            msg = "Temperature OK (%.2f/%.2f)"%(temperature.value,
                                                check.temperature) if not ret \
                else "Temperature lower than specified threshold(%.2f/%.2f)"%(temperature.value,
                                                check.temperature)
            return ret, msg
        elif check.mode == 1: # True if value is lower for more than the specified number of hours
            ret = check.temperature < temperature.value
            msg = "Nothing to do. Temperature lower than threshold (%.2f/%.2f)."%(temperature.value,
                                                                                  check.temperature) if not ret \
                else "Temperature higher than threshold (%.2f/%.2f)."%(temperature.value,check.temperature)

            if not ret:
                check.time = site.ut().replace(tzinfo=None)
            elif check.time is not None:
                ret = check.time + datetime.timedelta(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
                if ret:
                    msg += "Elapsed time ok"
                    check.time = site.ut().replace(tzinfo=None)
                else:
                    msg += "Elapsed time too short."
            else:
                check.time = site.ut().replace(tzinfo=None)
                ret = False

            return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class WindSpeedHandler(CheckHandler):
    '''
    This class checks if wind speed is above or bellow some threshold.

    Process will return True if wind speed is above specified threshold or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    @requires("weatherstations")
    def process(check):
        weatherstations = WindSpeedHandler.weatherstations
        site = WindSpeedHandler.site[0]

        manager = WindSpeedHandler.manager

        windspeed = None
        for i in range(len(weatherstations)):
            s = weatherstations[i].wind_speed()
            if datetime.datetime.utcnow() - s.time < datetime.timedelta(minutes=manager["max_mins"]):
                windspeed = s
                break
        if windspeed is None:
            return check.mode == 0, "No valid weather station data available!"

        if check.mode == 0:
            ret = check.windspeed < windspeed.value
            msg = "Wind speed OK (%.2f/%.2f)"%(windspeed.value,
                                               check.windspeed) if not ret \
                else "Wind speed higher than specified threshold (%.2f/%.2f)"%(windspeed.value,
                                               check.windspeed)
            return ret, msg

        elif check.mode == 1: # True if value is lower for more than the specified number of hours
            ret = check.windspeed > windspeed.value
            msg = "Nothing to do. Windspeed higher than threshold (%.2f/%.2f)."%(windspeed.value,check.windspeed) if not ret \
                else "Windspeed lower than threshold (%.2f/%.2f)."%(windspeed.value,check.windspeed)

            if not ret:
                check.time = site.ut().replace(tzinfo=None)
            elif check.time is not None:
                ret = check.time + datetime.timedelta(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
                if ret:
                    msg += "Elapsed time ok"
                    check.time = site.ut().replace(tzinfo=None)
                else:
                    msg += "Elapsed time too short."
            else:
                check.time = site.ut().replace(tzinfo=None)
                ret = False

            return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class DewPointHandler(CheckHandler):
    '''
    This class checks if dew point is above or bellow some threshold.

    Process will return True if dew point is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("weatherstations")
    def process(check):
        weatherstation = DewPointHandler.weatherstations

        ret = check.dewpoint > weatherstation.dew_point()
        msg = "Dew point OK" if not ret else "Dew point lower than specified threshold"
        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class TransparencyHandler(CheckHandler):
    '''
    This class checks if dew point is above or bellow some threshold.

    Process will return True if dew point is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("weatherstations")
    def process(check):
        weatherstations = WindSpeedHandler.weatherstations
        site = WindSpeedHandler.site[0]

        manager = WindSpeedHandler.manager

        transparency = None
        for i in range(len(weatherstations)):
            try:
                t = weatherstations[i].sky_transparency()
                if datetime.datetime.utcnow() - t.time < datetime.timedelta(minutes=manager["max_mins"]):
                    transparency = t
                    break
            except:
                pass

        if transparency is None:
            return check.mode == 0, "No valid weather station data available!"

        if check.mode == 0:
            ret = check.transparency > transparency.value
            msg = "Sky transparency OK (%.2f/%.2f)"%(transparency.value,
                                               check.transparency) if not ret \
                else "Sky transparency lower than specified threshold (%.2f/%.2f)"%(transparency.value,
                                                                                    check.transparency)
            return ret, msg

        elif check.mode == 1: # True if value is lower for more than the specified number of hours
            ret = check.transparency < transparency.value
            msg = "Nothing to do. Sky transparency lower than threshold (%.2f/%.2f)." % \
                  (transparency.value,check.transparency) if not ret \
                else "Sky transparency higher than threshold (%.2f/%.2f)."%(transparency.value,check.transparency)

            if not ret:
                check.time = site.ut().replace(tzinfo=None)
            elif check.time is not None:
                ret = check.time + datetime.timedelta(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
                if ret:
                    msg += "Elapsed time ok"
                    check.time = site.ut().replace(tzinfo=None)
                else:
                    msg += "Elapsed time too short."
            else:
                check.time = site.ut().replace(tzinfo=None)
                ret = False

            return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class AskListenerHandler(CheckHandler):

    @staticmethod
    def process(check):
        manager = AskListenerHandler.manager

        result = manager.askWatcher(check.question,check.waittime)

        ret = result.upper() == "OK"

        if ret:
            return ret,"User send OK. Proceeding..."
        else:
            return False,"Negated with %s" % result

class DewHandler(CheckHandler):
    '''
    This class checks if the difference between temperature and dew point is above or bellow some threshold.

    Process will return True if difference is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    @requires("weatherstations")
    def process(check):
        weatherstations = DewHandler.weatherstations
        site = DewHandler.site[0]

        temperature = None # weatherstation.temperature()
        dewpoint = None # weatherstation.dew_point()

        manager = DewHandler.manager

        for i in range(len(weatherstations)):
            t = weatherstations[i].temperature()
            d = weatherstations[i].dew_point()
            if datetime.datetime.utcnow() - t.time < datetime.timedelta(minutes=manager["max_mins"]):
                temperature = t
                dewpoint = d
                break
        if (temperature is None) or (dewpoint is None):
            return check.mode == 0, "No valid weather station data available!"

        tempdiff = ( temperature.value - dewpoint.value )

        if check.mode == 0:
            ret = check.tempdiff > tempdiff
            msg = "Dew OK (%.2f/%.2f)"%(tempdiff,
                                        check.tempdiff) if not ret \
                else "Dew point difference lower than specified threshold (%.2f/%.2f)"%(tempdiff,
                                        check.tempdiff)
            check.time = site.ut().replace(tzinfo=None)
            return ret, msg
        elif check.mode == 1: # True if value is lower for more than the specified number of hours
            ret = check.tempdiff < tempdiff
            msg = "Nothing to do. Dew point difference " \
                  "higher than threshold (%.2f/%.2f)."%(tempdiff, check.tempdiff) if not ret \
                else "Dew point difference lower than threshold (%.2f/%.2f)."%(tempdiff, check.tempdiff)

            if not ret:
                check.time = site.ut().replace(tzinfo=None)
            elif check.time is not None:
                ret = check.time + datetime.timedelta(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
                if ret:
                    msg += "Elapsed time ok"
                    check.time = site.ut().replace(tzinfo=None)
                else:
                    msg += "Elapsed time too short."
            else:
                check.time = site.ut().replace(tzinfo=None)
                ret = False

            return ret, msg
        else:
            check.time = site.ut().replace(tzinfo=None)
            return False, "Unrecognized mode %i." % check.mode

    @staticmethod
    def log(check):
        return "%s"%(check)


class DomeHandler(CheckHandler):
    '''
    This class checks if dome slit is open.

    Process will return True if dew point is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("dome")
    def process(check):
        dome = DomeHandler.dome[0]

        ret,msg = False, ""

        if check.mode == 0:
            ret = dome.isSlitOpen()
            msg = "Dome slit open" if ret else "Dome slit closed"
        elif check.mode == 1:
            ret = not dome.isSlitOpen()
            msg = "Dome slit closed" if ret else "Dome slit open"
        elif check.mode == 2:
            ret = dome.isFlapOpen()
            msg = "Dome flap open" if ret else "Dome flap closed"
        elif check.mode == 3:
            ret = not dome.isFlapOpen()
            msg = "Dome flap closed" if ret else "Dome flap open"

        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)


class TelescopeHandler(CheckHandler):
    '''
    This class checks telescope operations

    Process will return True if dew point is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("telescope")
    def process(check):
        telescope = TelescopeHandler.telescope[0]

        ret,msg = False, ""

        if check.mode == 1:
            ret = telescope.isParked()
            msg = "Telescope is parked." if ret else "Telescope is unparked"
        elif check.mode == -1:
            ret = not telescope.isParked()
            msg = "Telescope is unparked." if ret else "Telescope is parked"
        elif check.mode == 2:
            ret = telescope.isCoverOpen()
            msg = "Telescope cover is open" if ret else "Telescope cover is closed"
        elif check.mode == -2:
            ret = not telescope.isCoverOpen()
            msg = "Telescope cover is closed" if ret else "Telescope cover is open"
        elif check.mode == 3:
            ret = telescope.isSlewing()
            msg = "Telescope slewing" if ret else "Telescope not slewing"
        elif check.mode == -3:
            ret = not telescope.isSlewing()
            msg = "Telescope not slewing" if ret else "Telescope slewing"
        elif check.mode == 4:
            ret = telescope.isTracking()
            msg = "Telescope tracking" if ret else "Telescope not tracking"
        elif check.mode == -4:
            ret = not telescope.isTracking()
            msg = "Telescope not tracking" if ret else "Telescope tracking"


        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class CheckWeatherStationHandler(CheckHandler):

    @staticmethod
    @requires("weatherstations")
    def process(check):
        manager = CheckWeatherStationHandler.manager
        weatherstations = CheckWeatherStationHandler.weatherstations

        ws = weatherstations[check.index]

        t = ws.temperature()
        if check.mode == 0:
            # Check if WS is ok
            if datetime.datetime.utcnow() - t.time < datetime.timedelta(minutes=manager["max_mins"]):
                return True, "Weather station data OK!"
            else:
                return False, "No valid weather station data available!"
        elif check.mode == 1:
            # Check if WS is not OK
            if datetime.datetime.utcnow() - t.time < datetime.timedelta(minutes=manager["max_mins"]):
                return False, "Weather station data OK!"
            else:
                return True, "No valid weather station data available!"

    @staticmethod
    def log(check):
        return "%s" % check

class InstrumentFlagHandler(CheckHandler):

    @staticmethod
    def process(check):
        manager = InstrumentFlagHandler.manager
        from chimera_manager.controllers.status import InstrumentOperationFlag

        ret = False
        msg = ''

        if check.mode == 0:
            ret = manager.getFlag(check.instrument) == InstrumentOperationFlag.fromStr(check.flag.upper())
            msg = "%s: %s flag is %s" % (ret, check.instrument, check.flag.upper())
        elif check.mode == 1:
            ret = not ret
            msg = "%s: %s flag is %s" % (ret, check.instrument, check.flag.upper())
        elif check.mode == 2:
            # Check if instrument is locked with specified key
            ret = manager.hasKey(check.instrument, check.flag)
            msg = "%s is locked with key %s. " % (check.instrument, check.flag) if ret \
                else "%s is not locked with key %s. " % (check.instrument, check.flag)
        else:
            msg = "Mode %i not available" % check.mode

        return ret, msg

    @staticmethod
    def log(check):
        return '%s' % check