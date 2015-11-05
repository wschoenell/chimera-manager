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
    0 - Specify a reference time (in hours from ut = 0)
    1 - Sun set (sun setting @ alt 0)
    2 - Sun set twilight begin (sun setting @ alt -12)
    3 - Sun set twilight end (sun setting @ alt -18)
    4 - Sun rise (sun rising @ alt 0)
    5 - Sun rise twilight begin (sun setting @ alt -12)
    6 - Sun rise twilight end (sun setting @ alt -18)

    Process
    will return True if the
    sun is above the specified value or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    def process(check):
        site = TimeHandler.site

        reftime = check.time
        if check.mode == 1:
            reftime = site.sunset()
        elif check.mode == 2:
            reftime = site.sunset_wilight_begin()
        elif check.mode == 3:
            reftime = site.sunset_twilight_end()
        elif check.mode == 4:
            reftime = site.sunrise()
        elif check.mode == 5:
            reftime = site.sunrise_twilight_begin()
        elif check.mode == 6:
            reftime = site.sunrise_twilight_end()
        else:
            pass

        if reftime is None:
            return False,"Could not determined reference time."

        

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
    @requires("weatherstation")
    def process(check):
        weatherstation = HumidityHandler.weatherstation
        site = HumidityHandler.site

        humidity = weatherstation.humidity()
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
                    msg += "Elapsed time too short."
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
    @requires("weatherstation")
    def process(check):
        weatherstation = TemperatureHandler.weatherstation

        temperature = weatherstation.temperature()
        ret = check.temperature > temperature
        msg = "Temperature OK (%.2f/%.2f)"%(temperature.value,
                                            check.temperature) if not ret \
            else "Temperature lower than specified threshold(%.2f/%.2f)"%(temperature.value,
                                            check.temperature)
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
    @requires("weatherstation")
    def process(check):
        weatherstation = WindSpeedHandler.weatherstation

        windspeed = weatherstation.wind_speed()
        ret = check.windspeed < windspeed.value
        msg = "Wind speed OK (%.2f/%.2f)"%(windspeed.value,
                                           check.windspeed) if not ret \
            else "Wind speed higher than specified threshold (%.2f/%.2f)"%(windspeed.value,
                                           check.windspeed)
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
    @requires("weatherstation")
    def process(check):
        weatherstation = DewPointHandler.weatherstation

        ret = check.dewpoint > weatherstation.dew_point()
        msg = "Dew point OK" if not ret else "Dew point lower than specified threshold"
        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)

class DewHandler(CheckHandler):
    '''
    This class checks if the difference between temperature and dew point is above or bellow some threshold.

    Process will return True if difference is bellow specified threshold  or False, otherwise.
    '''
    @staticmethod
    @requires("weatherstation")
    def process(check):
        weatherstation = DewHandler.weatherstation

        temperature = weatherstation.temperature()
        dewpoint = weatherstation.dew_point()
        tempdiff = ( temperature.value - dewpoint.value )
        ret = check.tempdiff > tempdiff
        msg = "Dew OK (%.2f/%.2f)"%(tempdiff,
                                    check.tempdiff) if not ret \
            else "Dew point difference lower than specified threshold (%.2f/%.2f)"%(tempdiff,
                                    check.tempdiff)
        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)
