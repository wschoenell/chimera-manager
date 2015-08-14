
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
        site = CheckHandler.site

        # calculate mid day
        sunrise = site.MJD(site.sunrise())
        sunset = site.MJD(site.sunset())
        mid = (sunrise+sunset)/2.
        midnight = sunrise < sunset
        now = site.MJD()

        sun_pos = site.sunpos()

        if sun_pos.alt > check.sun_altitude:
            if (midnight and mid < now) or (not midnight and mid > now):
                return 0
            else:
                return 1
        else:
            if (midnight and mid < now) or (not midnight and mid > now):
                return 2
            else:
                return 3

    @staticmethod
    def log(check):
        return "Checking if sun is above %s degrees"%check.min_sun_alt