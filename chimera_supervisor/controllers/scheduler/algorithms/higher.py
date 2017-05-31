
from chimera_supervisor.controllers.scheduler.algorithms.base import *

class Higher(BaseScheduleAlgorith):

    @staticmethod
    def name():
        return 'HIG'

    @staticmethod
    def id():
        return 0

    @staticmethod
    def process(*args,**kwargs):
        log = logging.getLogger('sched-algorith(higher)')
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

        # Creat observation slots.

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

        #obsBlocks = np.zeros(len(obsSlots))-1

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

        '''
        radecArray = np.array([Position.fromRaDec(target[2].targetRa,
                                                 target[2].targetDec) for target in targets])'''

        mask = np.zeros(len(radecArray)) == 0
        #radecPos = np.arange(len(radecArray))
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

                # for item in items:
                #     pool.apply_async(worker, (item,))
                #
                # pool.close()
                # pool.join()
                pool = Pool(pool_size)

                for i in range(len(radecArray)):
                    # if i % 100 == 0:
                    #     log.debug('%i/%i'%(i,len(radecArray)))
                    #
                    # targetPar[i] = ( float(site.raDecToAltAz(radecArray[i],lst).alt),
                    #                  radecArray[i].angsep(moonRaDec),
                    #                  targets[i][1].minmoonDist,
                    #                  targets[i][1].minmoonBright < moonBrightness < targets[i][1].maxmoonBright )
                    pool.apply_async(worker,(i,))

                log.debug('Starting pool')
                pool.close()
                pool.join()
                log.debug('Pool done')

                # Create moon mask
                moonMask = np.bitwise_and(targetPar['moonD'] > targetPar['minmoonD'],targetPar['mask_moonBright'])

                # guarantee it is a copy not a reference...
                # tmp_Mask = np.bitwise_and(moonMask)
                mapping = np.arange(len(mask))[moonMask]
                tmp_radecArray = np.array(radecArray[moonMask], copy=True)
                tmp_radecPos = np.array(radecPos[moonMask], copy=True)

                if len(tmp_radecArray) == 0:
                    log.warning('Slot[%03i]: Could not find suitable target'%(itr+1))
                    continue

                #sitelat = np.sum(np.array([float(tt) / 60.**i for i,tt in enumerate(str(site['latitude']).split(':'))]))
                alt = targetPar['altitude'][moonMask] #np.array([float(site.raDecToAltAz(coords,lst).alt) for coords in tmp_radecArray])

                stg = alt.argmax()

                # while targets[:][radecPos[stg]][0].blockid in obsSlots['blockid']:
                #     log.warning('Observing block already scheduled... Should not be available! Looking for another one... Queue may be compromised...')
                #
                #     mask[stg] = False
                #     stg = alt[mask].argmax()

                # Check airmass
                airmass = 1./np.cos(np.pi/2.-alt[stg]*np.pi/180.)
                # Since this is the highest at this time, doesn't make
                # sense to iterate over it
                if airmass > targets[:][radecPos[stg]][1].maxairmass or airmass < 0.:
                    log.info('Object too low in the sky, (Alt.=%6.2f) airmass = %5.2f (max = %5.2f)... Skipping this slot..'%(alt[stg],airmass,targets[:][radecPos[stg]][1].maxairmass))

                    continue

                # Now, this one makes sense to iterate over.. But, a target
                # that is too close to the moon now, may not be in the
                # future, so, need to keep it in the list. That's why we
                # use temporary arrays...
                # s_target = targets[:][tmp_radecPos[stg]]

                # while ( (tmp_radecArray[stg].angsep(moonRaDec) < s_target[1].minmoonDist)  ):
                #     if len(tmp_Mask) == 0:
                #         break
                #     msg = '''Target %s %s cannot be observed due to moon restrictions (d = %.2f < %.2f). Moon @ %s (Phase: %.2f)'''
                #     log.warning(msg%(s_target[0],
                #                      s_target[2],
                #                      tmp_radecArray[stg].angsep(moonRaDec),
                #                      s_target[1].minmoonDist,
                #                      moonRaDec,
                #                      moonBrightness))
                #     tmp_Mask[stg] = False
                #     tmp_radecArray = tmp_radecArray[tmp_Mask]
                #     tmp_radecPos = tmp_radecPos[tmp_Mask]
                #     alt = alt[tmp_Mask]
                #     stg = alt.argmax()
                #     tmp_Mask = tmp_Mask[tmp_Mask]
                #     # Check airmass
                #     airmass = 1./np.cos(np.pi/2.-alt[stg]*np.pi/180.)
                #     if airmass > targets[:][radecPos[stg]][1].maxairmass:
                #         log.info('New object too low in the sky, (Alt.=%6.2f) airmass = %5.2f (max = %5.2f)...'%(alt[stg],airmass,targets[:][radecPos[stg]][1].maxairmass))
                #
                #         tmp_Mask = [] # empty tmp mask. This is the highest! No sense going on...
                #         break
                #     s_target = targets[:][tmp_radecPos[stg]]

                s_target = targets[tmp_radecPos[stg]]

                log.info('Slot[%03i] @%.3f: %s %s (Alt.=%6.2f, airmass=%5.2f (max=%5.2f))'%(itr+1,obsSlots['start'][itr],s_target[0],s_target[2],alt[stg],airmass,s_target[1].maxairmass))

                mask[mapping[stg]] = False
                radecArray = radecArray[mask]
                radecPos = radecPos[mask]
                moonPar = moonPar[mask]
                mask = mask[mask]
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

                '''
                if not targets[stg][0].blockid in obsTargets['blockid']:
                    #log.debug('#%s %i %i %f: lst = %f | ra = %f | scheduled = %i'%(s_target[0].pid,stg,targets[:][stg][0].blockid,obsSlots['start'][itr],lst,s_target[1].targetRa,targets[:][stg][0].scheduled))
                    log.info('Slot[%03i]: %s'%(itr+1,s_target[2]))

                    #obsTargets = np.append( obsTargets, np.array((s_target[0],s_target[1],targets[stg][0].blockid),dtype=[('obsblock',ObsBlock),('targets',Targets),('blockid',np.int)]))

                    #self.addObservation(s_target[0],obsSlots['start'][itr])
                    targets[stg][0].scheduled = True

                else:
                    log.debug('#Block already scheduled#%s %i %i %f: lst = %f | ra = %f | scheduled = %i'%(s_target[0].pid,stg,targets[stg][0].blockid,obsSlots['start'][itr],lst,s_target[1].targetRa,targets[stg][0].scheduled))
                '''
            #targets = targets.filter(ObsBlock.scheduled == False)
            else:
                log.warning('Observing slot[%i]@%.4f is already filled with block id %i...'%(itr,
                                                                                             obsSlots['start'][itr],
                                                                                             obsSlots['blockid'][itr]))

        return obsSlots

    @staticmethod
    def next(time, programs):

        dt = np.array([ np.abs(time - program[0].slewAt) for program in programs])
        iprog = np.argmin(dt)
        return programs[iprog]
        # lst = Higher.site.LST(datetimeFromJD(time+2400000.5)).H
        # ah = np.array([ np.abs(lst - program[3].targetRa) for program in programs])
        # iprog = np.argmin(ah)
        # return programs[iprog]

    @staticmethod
    def observed(time, program, site = None, soft = False):
        '''
        Process program as observed.

        :param program:
        :return:
        '''
        session = Session()
        obsblock = session.merge(program[2])
        obsblock.observed = True
        if not soft:
            obsblock.completed= True
            obsblock.lastObservation = site.ut().replace(tzinfo=None)
        session.commit()

