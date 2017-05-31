import os
import numpy as np
import yaml
from sqlalchemy import or_, and_
import datetime

from chimera_supervisor.controllers.scheduler.model import ObsBlock, ExtMoniDB, ObservedAM, TimedDB, RecurrentDB, Session
from chimera.util.enum import Enum
from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY
from chimera.core.site import datetimeFromJD
from chimera.core.exceptions import ChimeraException
from chimera.util.position import Position
from chimera.util.coord import Coord
from chimera.util.output import blue, green, red
import logging
from multiprocessing.pool import ThreadPool as Pool

ScheduleOptions = Enum("HIG","STD")

class ExtintionMonitorException(ChimeraException):
    pass

class TimedException(ChimeraException):
    pass

fileHandler = logging.handlers.RotatingFileHandler(os.path.join(SYSTEM_CONFIG_DIRECTORY,
                                      "scheduler_algorithms.log"),
                                                       maxBytes=100 *
                                                       1024 * 1024,
                                                       backupCount=10)

# _log_handler = logging.FileHandler(fileHandler)
fileHandler.setFormatter(logging.Formatter(fmt='%(asctime)s[%(levelname)s:%(threadName)s]-%(name)s-(%(filename)s:%(lineno)d):: %(message)s'))
fileHandler.setLevel(logging.DEBUG)
# self.debuglog.addHandler(fileHandler)
# self.debuglog.setLevel(logging.DEBUG)

class RecurrentAlgorithException(ChimeraException):
    pass

class BaseScheduleAlgorith():

    @staticmethod
    def name():
        return 'BASE'

    @staticmethod
    def id():
        return -1

    @staticmethod
    def process(*args,**kwargs):
        pass

    @staticmethod
    def merit_figure(target):
        pass

    @staticmethod
    def next(time,programs):
        '''
        Select the program to observe with this scheduling algorithm.

        :param time:
        :param programs:
        :return:
        '''
        pass

    @staticmethod
    def observed(time, program, site = None, soft = False):
        '''
        Process program as observed.

        :param program:
        :return:
        '''
        pass

    @staticmethod
    def add(block):
        '''
        Process block to add it to the queue.

        :param block:
        :return:
        '''
        pass

    @staticmethod
    def clean(pid):
        '''
        Hard clean any schedule routine. Wipe all information from database
        :return:
        '''
        pass

    @staticmethod
    def soft_clean(pid,block=None):
        '''
        Soft clean any schedule routine. This will only erase information about observations.
        :return:
        '''
        pass

    @staticmethod
    def model():
        pass


def Airmass(alt):

    am = 1./np.cos(np.pi/2.-alt*np.pi/180.)
    if am < 0.:
        am = 999.
    return am
