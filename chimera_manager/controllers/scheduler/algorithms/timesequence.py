from chimera_manager.controllers.scheduler.algorithms.base import *
from chimera_manager.controllers.scheduler.algorithms.higher import Higher


class TimeSequence(BaseScheduleAlgorith):
    '''
    Provide scheduler algorithm for time sequence observations. This is designed to provide time monitoring on targets.
     A target will be retrofed into the scheduler while it is the higher in the sky, given the observational conditions.
     It is also possible to set a maximum number of visits on each field.
    '''

    @staticmethod
    def name():
        return 'TIMESEQUENCE'

    @staticmethod
    def id():
        return 4

    @staticmethod
    def process(*args, **kwargs):
        log = logging.getLogger('sched-algorith(timesequence.process)')
        log.addHandler(fileHandler)

        slotLen = 60.
        if 'slotLen' in kwargs.keys():
            slotLen = kwargs['slotLen']
        elif len(args) > 1:
            try:
                slotLen = float(args[0])
            except:
                slotLen = 60.

        pool_size = 1
        max_sched_blocks = -1
        if 'config' in kwargs:
            config = kwargs['config']
            if 'pool_size' in config:
                pool_size = config['pool_size']

            if 'slotLen' in config:
                slotLen = config['slotLen']


            if 'max_sched_blocks' in config:
                max_sched_blocks = config['max_sched_blocks']

        nightstart = kwargs['obsStart']
        nightend   = kwargs['obsEnd']
        site = kwargs['site']

        # Create observation slots.

        obsSlots = np.array(np.arange(nightstart,nightend,slotLen/60./60./24.),
                            dtype= [ ('start',np.float),
                                     ('end',np.float)  ,
                                     ('slotid',np.int) ,
                                     ('blockid',np.int)] )

        log.debug('Creating %i observing slots'%(len(obsSlots)))

        obsSlots['end'] += slotLen/60./60/24.
        obsSlots['slotid'] = np.arange(len(obsSlots))
        obsSlots['blockid'] = np.zeros(len(obsSlots))-1

        '''
        obsTargets = np.array([],dtype=[('obsblock',ObsBlock),
                                        ('targets',Targets),
                                        ('blockid',np.int)])'''

        # For each slot select the higher in the sky...

        targets = kwargs['query']

        radecArray = np.array([Position.fromRaDec(targets[:][0][2].targetRa,
                                                  targets[:][0][2].targetDec)])

        moonPar = np.array([( target[1].minmoonDist,
                              target[1].minmoonBright ,
                              target[1].maxmoonBright,
                              target[0].length) for target in targets[:]],
                           dtype=[('minmoonDist',np.float),
                                  ('minmoonBright',np.float),
                                  ('maxmoonBright',np.float),
                                  ('lenght',np.float)])

        radecPos = np.array([0])

        blockid = targets[:][0][0].blockid

        for itr,target in enumerate(targets):
            if blockid != target[0].blockid:
                radecArray =  np.append(radecArray,Position.fromRaDec(target[2].targetRa,
                                                                      target[2].targetDec))
                blockid = target[0].blockid
                radecPos = np.append(radecPos,itr)


        mask = np.zeros(len(radecArray)) == 0
        nblocks_scheduled = 0

        for itr in range(len(obsSlots)):

            # this "if" is the key to multitarget blocks...
            if obsSlots['blockid'][itr] == -1:

                dateTime = datetimeFromJD(obsSlots['start'][itr])

                lst = site.LST_inRads(dateTime) # in radians

                # This loop is really slow! Must think of a way to speed
                # things up...

                # Apply moon exclusion radius..
                moonPos = site.moonpos(dateTime)
                moonRaDec = site.altAzToRaDec(moonPos,lst)

                moonBrightness = site.moonphase(dateTime)*100.

                if (
                    (not (moonPar['minmoonBright'].max() < moonBrightness < moonPar['maxmoonBright'].min())) and
                        (moonPos.alt > 0.)
                    ):
                    log.warning('Slot[%03i]: Moon brightness (%5.1f%%) out of range (%5.1f%% -> %5.1f%%). \
    Moon alt. = %6.2f. Skipping this slot...'%(itr+1,
                                      moonBrightness,
                                      moonPar['minmoonBright'].max(),
                                      moonPar['maxmoonBright'].min(),
                                      moonPos.alt))
                    continue

                # Calculate target parameters
                log.debug('Starting slow loop')

                targetPar = np.zeros(len(radecArray),
                                     dtype=[('altitude',np.float),
                                                 ('moonD',np.float),
                                                 ('minmoonD',np.float),
                                                 ('mask_moonBright',np.bool)])

                def worker(index):
                    try:
                        time_offset = Coord.fromAS(moonPar['lenght'][index])
                        log.debug('%s %s %s' % (lst, time_offset.R, time_offset.H))
                        targetPar[index] = (
                            float(site.raDecToAltAz(radecArray[index],lst+time_offset.R/2.).alt),
                            radecArray[index].angsep(moonRaDec),
                            moonPar['minmoonDist'][index],
                            ((moonPar['minmoonBright'][index] < moonBrightness < moonPar['maxmoonBright'][index])
                             or (moonPos.alt < 0.))
                        )
                    except Exception, e:
                        log.exception(e)

                pool = Pool(pool_size)

                for i in range(len(radecArray)):
                    pool.apply_async(worker,(i,))

                log.debug('Starting pool')
                pool.close()
                pool.join()
                log.debug('Pool done')

                # Create moon mask
                moonMask = np.bitwise_and(targetPar['moonD'] > targetPar['minmoonD'],targetPar['mask_moonBright'])

                # guarantee it is a copy not a reference...
                mapping = np.arange(len(mask))[moonMask]
                tmp_radecArray = np.array(radecArray[moonMask], copy=True)
                tmp_radecPos = np.array(radecPos[moonMask], copy=True)

                if len(tmp_radecArray) == 0:
                    log.warning('Slot[%03i]: Could not find suitable target'%(itr+1))
                    continue

                alt = targetPar['altitude'][moonMask]

                stg = alt.argmax()

                # Check airmass
                airmass = 1./np.cos(np.pi/2.-alt[stg]*np.pi/180.)
                # Since this is the highest at this time, doesn't make
                # sense to iterate over it
                if airmass > targets[:][radecPos[stg]][1].maxairmass or airmass < 0.:
                    log.info('Object too low in the sky, (Alt.=%6.2f) airmass = %5.2f (max = %5.2f)... Skipping this slot..'%(alt[stg],airmass,targets[:][radecPos[stg]][1].maxairmass))

                    continue

                s_target = targets[tmp_radecPos[stg]]

                log.info('Slot[%03i] @%.3f: %s %s (Alt.=%6.2f, airmass=%5.2f (max=%5.2f))'%(itr+1,obsSlots['start'][itr],s_target[0],s_target[2],alt[stg],airmass,s_target[1].maxairmass))

                # In this algorithm, differently from "HIGHER", a target that is selected now is kept in the queue
                # so it can be scheduled again in the next slot, in case it is also the best one, thus building a
                # time monitoring sequence.
                
                obsSlots['blockid'][itr] = s_target[0].blockid
                nblocks_scheduled += 1
                if max_sched_blocks > 0 and nblocks_scheduled >= max_sched_blocks:
                    log.info('Maximum number of scheduled blocks (%i) reached. Stopping.' % max_sched_blocks)
                    break


                # Check if this block has more targets...
                secTargets = targets.filter(ObsBlock.blockid == s_target[0].blockid,
                                            ObsBlock.objid != s_target[0].objid)

                if secTargets.count() > 0:
                    log.debug(red('Secondary targets not implemented yet...'))
                    pass

                if len(mask) == 0:
                    break

            else:
                log.warning('Observing slot[%i]@%.4f is already filled with block id %i...'%(itr,
                                                                                             obsSlots['start'][itr],
                                                                                             obsSlots['blockid'][itr]))

        return obsSlots

    @staticmethod
    def next(time, programs):
        log = logging.getLogger('sched-algorith(timesequence.next)')
        log.addHandler(fileHandler)

        log.debug('Using higher algorithm to select next target...')

        for prog in programs:
            log.debug('%s' % prog[0])

        return Higher.next(time, programs)

    @staticmethod
    def observed(time, program, site=None, soft=False):
        '''
        In this case, never marks a program as observed. So it can go back to the queue as long as it is the most
        suitable one.

        :param time:
        :param program:
        :param site:
        :param soft:
        :return:
        '''
        session = Session()

        try:
            block = session.merge(program[2])
            # block.observed = True
            if not soft:
                block.lastObservation = site.ut().replace(tzinfo=None)
            # Todo: Mark as observed after a specified number of visits
        finally:
            session.commit()

