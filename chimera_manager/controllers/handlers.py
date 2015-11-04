from datetime import timedelta as td

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
    This class checks if the sun is above or bellow some altitude threshould and if it is rising or setting.

    Return map is:
    0 - Sun above threshould rising
    1 - Sun above threshould setting
    2 - Sun bellow threshould rising
    3 - Sun bellow threshould setting

    Process
    will return True if the
    sun is above the specified value or False, otherwise.
    '''
    @staticmethod
    @requires("site")
    def process(check):
        site = TimeHandler.site

        # calculate mid day
        sunrise = site.MJD(site.sunrise())
        sunset = site.MJD(site.sunset())
        mid = (sunrise+sunset)/2.
        midnight = sunrise < sunset
        now = site.MJD()

        sun_pos = site.sunpos()

        status = 0

        if sun_pos.alt.D > check.sun_altitude:

            if (midnight and mid < now) or (not midnight and mid > now):
                return True if check.above and check.rising else False, "Sun above threshold rising"
            else:
                return True if check.above and not check.rising else False, "MJD: %f | Sun @ %s. Above threshold setting"%(now,sun_pos)
        else:
            if (midnight and mid < now) or (not midnight and mid > now):
                return True if not check.above and check.rising else False, "Sun bellow threshold rising"
            else:
                return True if not check.above and not check.rising else False, "Sun bellow threshold setting"


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
                ret = check.time + td(hours=check.deltaTime) < site.ut().replace(tzinfo=None)
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
