
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
    @requires("weatherstation")
    def process(check):
        weatherstation = HumidityHandler.weatherstation

        ret = check.humidity < weatherstation.humidity()
        msg = "Humidity OK" if ret else "Humidity higher than specified threshold"
        return ret, msg

    @staticmethod
    def log(check):
        return "%s"%(check)
