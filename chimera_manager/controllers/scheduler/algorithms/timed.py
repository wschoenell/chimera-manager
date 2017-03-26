
from chimera_manager.controllers.scheduler.algorithms.base import *
from chimera_manager.controllers.scheduler.algorithms.higher import Higher

class Timed(BaseScheduleAlgorith):

    '''
    Provide scheduler algorithm for observations at specific times (in seconds) with respect to night start twilight.
    '''

    @staticmethod
    def name():
        return 'TIMED'

    @staticmethod
    def id():
        return 2

    @staticmethod
    def process(*args,**kwargs):
        log = logging.getLogger('sched-algorith(timed)')
        log.addHandler(fileHandler)

        # Try to read times from the database. If none is provided, raise an exception
        if 'config' not in kwargs:
            raise TimedException("No configuration file provided.")

        config = kwargs['config']

        nightstart = kwargs['obsStart']
        nightend   = kwargs['obsEnd']


        for i in range(len(config['times'])):
            execute_at = nightstart-2400000.5+(config['times'][i]/24.)
            print execute_at
            config['times'][i] = execute_at

        slotLen = 1800.
        if 'slotLen' in kwargs.keys():
            slotLen = kwargs['slotLen']
        elif len(args) > 1:
            try:
                slotLen = float(args[0])
            except:
                slotLen = 1800.

        # Select targets with the Higher algorithm
        programs = Higher.process(slotLen=slotLen,*args,**kwargs)

        session = Session()
        # Store desired times in the database
        try:
            for obs_times in config['times']:
                if obs_times > nightend:
                    log.warning('Request for observation after the end of the night.')

                print('Requesting observation @ %.3f' % obs_times)
                timed = TimedDB(pid = config['pid'],
                                execute_at=obs_times)
                session.add(timed)
            return programs
        finally:
            session.commit()


    @staticmethod
    def next(time,programs):

        session = Session()

        try:
            program = session.merge(programs[0][0])
            timed_observation = session.query(TimedDB).filter(TimedDB.finished == False,
                                                               TimedDB.pid == program.pid).order_by(
                TimedDB.execute_at).first()

            if timed_observation is None:
                return None

            program_list = Higher.next(time,programs)

            program = session.merge(program_list[0])

            # Again, use higher to select a target but replace slewAt by execute_at.

            program.slewAt = timed_observation.execute_at

            obsblock = session.merge(program_list[2])
            timed_observation.tid = program.tid
            timed_observation.blockid = obsblock.id

            return program_list

        finally:
            session.commit()

    @staticmethod
    def observed(time, program, site = None, soft = False):

        session = Session()

        try:
            prog = session.merge(program[0])
            block = session.merge(program[2])
            block.observed = True
            if not soft:
                block.lastObservation = site.ut().replace(tzinfo=None)

            timed_observations = session.query(TimedDB).filter(TimedDB.pid == prog.pid,
                                                               TimedDB.blockid == block.id,
                                                               TimedDB.tid == prog.tid,
                                                               TimedDB.finished == False).order_by(
                TimedDB.execute_at).first()

            if (timed_observations is not None):
                timed_observations.finished = True

        finally:
            session.commit()

    @staticmethod
    def soft_clean(pid,block=None):
        '''
        Soft clean any schedule routine. This will only erase information about observations.
        :return:
        '''
        session = Session()

        try:
            timed_observations = session.query(TimedDB).filter(TimedDB.pid == pid,
                                                               TimedDB.finished == True)

            if (timed_observations is not None):
                for timed in timed_observations:
                    timed.finished = False

        finally:
            session.commit()

    @staticmethod
    def clean(pid):
        '''
        Hard clean any schedule routine. Wipe all information from database
        :return:
        '''
        session = Session()

        try:
            timed_observations = session.query(TimedDB).filter(TimedDB.pid == pid)

            if (timed_observations is not None):
                for timed in timed_observations:
                    session.delete(timed)

        finally:
            session.commit()