
from chimera_supervisor.controllers.scheduler.algorithms.base import *
from chimera_supervisor.controllers.scheduler.algorithms.higher import Higher

class Recurrent(BaseScheduleAlgorith):

    '''
    Provide scheduler algorithm for recurrent observations. Targets are only scheduled if they where never observed
    or observed a specified time in the past.
    '''

    @staticmethod
    def name():
        return 'RECURRENT'

    @staticmethod
    def id():
        return 3

    @staticmethod
    def process(*args,**kwargs):
        log = logging.getLogger('sched-algorith(recurrent.process)')
        log.addHandler(fileHandler)

        # Try to read recurrency time from the configuration. If none is provided, raise an exception
        if ('config' not in kwargs) or ('recurrence' not in kwargs['config']):
            raise RecurrentAlgorithException("No configuration file provided or no recurrence time defined.")

        config = kwargs['config']

        nightstart = kwargs['obsStart']
        nightend   = kwargs['obsEnd']

        recurrence_time = config['recurrence']

        slotLen = 1800.
        if 'slotLen' in kwargs.keys():
            slotLen = kwargs['slotLen']
        elif len(args) > 1:
            try:
                slotLen = float(args[0])
            except:
                slotLen = 1800.
        elif 'slotLen' in config:
            slotLen = config['slotLen']
        from chimera_supervisor.controllers.scheduler.model import Targets,ObsBlock
        # Filter target by observing data. Leave "NeverObserved" and those observed more than recurrence_time days ago
        today = kwargs['site'].ut().replace(tzinfo=None)
        if 'today' in kwargs: # Needed for simulations...
            today = kwargs['today'].replace(tzinfo=None)
        reference_date = today - datetime.timedelta(days=recurrence_time)

        ntargets = len(kwargs['query'][:])
        # Exclude targets that where observed less then a specified ammount of time
        kwargs['query'] = kwargs['query'].filter(or_(ObsBlock.observed == False,
                                                     and_(ObsBlock.observed == True,
                                                          ObsBlock.lastObservation < reference_date)))
        new_ntargets = len(kwargs['query'][:])
        log.debug('Filtering %i of %i targets' % (new_ntargets, ntargets))
        # Select targets with the Higher algorithm
        programs = Higher.process(slotLen=slotLen,*args,**kwargs)

        return programs


    @staticmethod
    def next(time,programs):
        '''
        Select the program to observe with this scheduling algorithm.

        :param time:
        :param programs:
        :return:
        '''

        return Higher.next(time,programs)

    @staticmethod
    def add(block):
        session = Session()

        obsblock = session.merge(block[0])

        # Check if this is already in the database
        recurrent_block = session.query(RecurrentDB).filter(RecurrentDB.pid == obsblock.pid,
                                                          RecurrentDB.blockid == obsblock.id,
                                                          RecurrentDB.tid == obsblock.objid).first()

        if recurrent_block is None:
            # Not in the database, add it
            recurrent_block = RecurrentDB()
            recurrent_block.pid = obsblock.pid
            recurrent_block.blockid = obsblock.id
            recurrent_block.tid = obsblock.objid
            session.add(recurrent_block)

        session.commit()

    @staticmethod
    def observed(time, program, site = None, soft = False):
        '''
        Process program as observed.

        :param program:
        :return:
        '''
        log = logging.getLogger('sched-algorith(recurrent.observed)')
        log.addHandler(fileHandler)

        obstime = datetimeFromJD(time+2400000.5) #site.ut().replace(tzinfo=None) # get time and function entry

        session = Session()
        obsblock = session.merge(program[2])
        obsblock.observed = True

        log.debug('%s: Marking as observed @ %s' % (obsblock.pid, obstime))

        if not soft:
            log.debug('Running in hard mode. Storing main information in database.')
            # prog = session.merge(program[0])
            obsblock.observed = True
            obsblock.lastObservation = obstime.replace(tzinfo=None)

            # obsblock.completed= True
            obsblock.lastObservation = obstime
            reccurent_block = session.query(RecurrentDB).filter(RecurrentDB.pid == obsblock.pid,
                                                                RecurrentDB.blockid == obsblock.id,
                                                                RecurrentDB.tid == obsblock.objid).first()
            if reccurent_block is None:
                log.debug('Block not in recurrent database. Adding block...')
                print obsblock.blockid
                reccurent_block = RecurrentDB()
                reccurent_block.pid = obsblock.pid
                reccurent_block.blockid = obsblock.id,
                reccurent_block.tid = obsblock.objid
                reccurent_block.visits = 1
                reccurent_block.lastVisit = obstime
                session.add(reccurent_block)
            else:
                reccurent_block.visits += 1
                reccurent_block.lastVisit = obstime

                if 0 < reccurent_block.max_visits < reccurent_block.visits:
                    log.debug('Max visits (%i) reached. Marking as complete.' % reccurent_block.max_visits)
                    obsblock.completed = True
                else:
                    log.debug('%i visits completed.' % reccurent_block.visits)
        else:
            log.debug('Running in soft mode...')
            block = session.merge(program[2])
            block.observed = True

        session.commit()

