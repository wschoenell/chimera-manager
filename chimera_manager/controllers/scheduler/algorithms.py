
import numpy as np

from chimera_manager.controllers.scheduler.model import ObsBlock
from chimera.util.enum import Enum
from chimera.core.site import datetimeFromJD
from chimera.util.position import Position
from chimera.util.output import blue, green, red
import logging as log
from multiprocessing.pool import ThreadPool as Pool

pool_size = 5  # your "parallelness"

ScheduleOptions = Enum("HIG","STD")

def ScheduleFunction(opt,*args,**kwargs):

    sAlg = ScheduleOptions[opt]

    if sAlg == ScheduleOptions.HIG:

        def high(slotLen=60.):

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
                                  target[1].maxmoonBright ) for target in targets[:]],
                               dtype=[('minmoonDist',np.float),
                                      ('minmoonBright',np.float),
                                      ('maxmoonBright',np.float)])

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
                            targetPar[index] = (
                                float(site.raDecToAltAz(radecArray[index],lst).alt),
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

        return high

    if sAlg == ScheduleOptions.STD:

        def std(slotLen=60.):

            # [TBD] Reject objects that are close to the moon

            # Selecting standard stars is not only searching for the higher in that
            # time but select stars than can be observed at 3 or more (nairmass)
            # different airmasses. It is also important to select stars with
            # different colors (but this will be taken care in the future).

            # [TBD] Select by color also
            nightstart = kwargs['obsStart']
            nightend   = kwargs['obsEnd']
            site = kwargs['site']
            targets = kwargs['query']
            # [TBD] Read this parameters from a file
            nstars = 3
            nairmass = 3
            MINALTITUDE = 10.
            MAXAIRMASS = 1./np.cos(np.pi/2.-np.pi/18.)

            radecArray = np.array([Position.fromRaDec(targets[:][0][2].targetRa,
                                                      targets[:][0][2].targetDec)])

            # sort = np.argsort(targets[:][0][2].targetRa)
            # radecArray = radecArray[sort]

            targetNameArray = np.array([targets[:][0][2].name])

            # Creat observation slots.
            slotDtype = [ ('start',np.float),
                          ('end',np.float)  ,
                          ('slotid',np.int) ,
                          ('blockid',np.int),
                          ('filled',np.int)]
            obsSlots = np.array([],
                                  dtype= slotDtype)


            blockid = targets[:][0][0].blockid
            radecPos = np.array([0])
            blockidList = np.array([blockid])
            blockDuration = np.array([0]) # store duration of each block
            maxAirmass = np.array([targets[:][0][1].maxairmass]) # store max airmass of each block
            minAirmass = np.array([targets[:][0][1].minairmass]) # store max airmass of each block
            if maxAirmass[0] < 0:
                maxAirmass[0] = MAXAIRMASS
            if minAirmass[0] < 0:
                minAirmass[0] = MAXAIRMASS # ignore minAirmaa if not set

            # Get single block ids and determine block duration
            for itr,target in enumerate(targets):
                if blockid != target[0].blockid:
                    radecArray =  np.append(radecArray,Position.fromRaDec(target[2].targetRa,
                                                                          target[2].targetDec))
                    targetNameArray = np.append(targetNameArray,target[2].name)
                    blockid = target[0].blockid
                    radecPos = np.append(radecPos,itr)
                    blockidList = np.append(blockidList,blockid)
                    if target[1].maxairmass > 0:
                        maxAirmass = np.append(maxAirmass,target[1].maxairmass)
                    else:
                        maxAirmass = np.append(maxAirmass,
                                               MAXAIRMASS)

                    if target[1].minairmass > 0:
                        minAirmass = np.append(minAirmass,target[1].minairmass)
                    else:
                        minAirmass = np.append(minAirmass,
                                               MAXAIRMASS) # ignored if not set

                    blockDuration = np.append(blockDuration,0.)

                blockDuration[-1]+=(target[3].exptime*target[3].nexp)

            # Start allocating
            ## get lst at meadle of the observing window
            midnight = (nightstart+nightend)/2.
            dateTime = datetimeFromJD(midnight)
            lstmid = site.LST_inRads(dateTime) # in radians

            nalloc = 0 # number of stars allocated
            nblock = 0 # block iterator
            nballoc = 0 # total number of blocks allocated

            while nalloc < nstars and nblock < len(radecArray):
            # while nblock < len(radecArray):
                # get airmasses
                olst = np.float(radecArray[nblock].ra)*np.pi/180.*0.999
                maxAltitude = float(site.raDecToAltAz(radecArray[nblock],
                                                      olst).alt)
                minAM = 1./np.cos(np.pi/2.-maxAltitude*np.pi/180.)

                log.debug("Altitute max/min: %.2f/%.2f" % (maxAltitude,MINALTITUDE))
                log.debug("Airmass max/min: %.2f/%.2f" % (maxAirmass[nblock],minAM))

                log.debug('Working on: %s'%targetNameArray[nblock])

                if maxAltitude < MINALTITUDE:
                    nblock+=1
                    log.debug('Max altitude %6.2f lower than minimum: %s'%(float(radecArray[nblock].ra),radecArray[nblock]))
                    continue
                elif minAM > minAirmass[nblock]:
                #    nblock+=1
                    log.warning('Min airmass %7.3f higher than minimum: %7.3f'%(minAM,minAirmass[nblock]))
                #    continue

                # set desired airmasses
                dairMass = np.linspace(minAM,maxAirmass[nblock]*0.9,nairmass)

                # Decide the start and end times for allocation
                start = nightstart
                end = nightend

                # if olst > lstmid:
                #     end = midnight+(olst-lstmid)*12./np.pi/24.
                # else:
                #     start = midnight-(lstmid-olst)*12./np.pi/24.

                # find times where object is at desired airmasses
                allocateSlot = np.array([],
                                          dtype= slotDtype)

                start = nightstart if start < nightstart else start
                end = nightend if end > nightend else end
                log.debug('Trying to allocate %s'%(radecArray[nblock]))
                nballoc_tmp = nballoc
                time_grid = np.arange(nightstart,nightend,slotLen/60./60./24.)
                lst_grid = [site.LST_inRads(datetimeFromJD(tt)) for tt in time_grid]
                airmass_grid = np.array([Airmass(float(site.raDecToAltAz(radecArray[nblock],
                                                             lst).alt)) for lst in lst_grid])
                min_amidx = np.min(airmass_grid)
                for dam in dairMass:

                    # Before culmination

                    converged = False
                    dam_grid = np.abs(airmass_grid[:min_amidx]-dam)
                    mm = dam_grid < maxAirmass[maxAirmass[nblock]]
                    dam_grid[mm] = np.max(dam_grid)
                    dam_pos = np.argmin(np.abs(airmass_grid[:min_amidx]-dam))
                    if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                        time = time_grid[dam_pos]
                        converged = True
                    else:
                        dam_pos = np.argmin(np.abs(airmass_grid-dam))
                        mm = dam_grid < maxAirmass[maxAirmass[nblock]]
                        dam_grid[mm] = np.max(dam_grid)
                        if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                            time = time_grid[dam_pos]
                            converged = True
                    print converged,time


                    # time = (start+end)/2.
                    # am = dam+1.
                    # niter = 0
                    # converged = True
                    # oldam = am
                    # while np.abs(am-dam) > 1e-1:
                    #     time = (start+end)/2.
                    #     lst_start = site.LST_inRads(datetimeFromJD(start)) # in radians
                    #     lst_end = site.LST_inRads(datetimeFromJD(end)) # in radians
                    #     lst = site.LST_inRads(datetimeFromJD(time)) # in radians
                    #     amStart = Airmass(float(site.raDecToAltAz(radecArray[nblock],
                    #                                          lst_start).alt))
                    #     amEnd = Airmass(float(site.raDecToAltAz(radecArray[nblock],
                    #                  lst_end).alt))
                    #     am = Airmass(float(site.raDecToAltAz(radecArray[nblock],
                    #                                          lst).alt))
                    #     niter += 1
                    #     log.debug('%.5f %.3f | %.5f %.3f | %.5f %.3f'%(start,amStart,time,am,end,amEnd))
                    #
                    #     if amStart > amEnd:
                    #         if am > dam:
                    #             start = time
                    #         else:
                    #             end = time
                    #     else:
                    #         if am > dam:
                    #             end = time
                    #         else:
                    #             start = time
                    #
                    #     if niter > 1000:
                    #         log.error('Could not converge on search for airmass...')
                    #         converged = False
                    #         break
                    #     elif abs(oldam-am) < 1e-5:
                    #         log.error('Could not converge on search for airmass...')
                    #         converged = False
                    #         break
                    #
                    #     oldam = am

                    if not converged:
                        break

                    filled = False
                    # Found time, try to allocate
                    for islot in range(len(obsSlots)):
                        if obsSlots['start'][islot] < time < obsSlots['end'][islot]:
                            filled = True
                            log.debug('Slot[%i] filled %.3f/%.3f @ %.3f'%(islot,
                                                                          obsSlots['start'][islot],
                                                                          obsSlots['end'][islot],
                                                                          time))
                            break

                    if not filled:
                        # Check that it comply with block constraints
                        # Airmass should be ok since allocation is airmass based
                        # so we only need to check moon distance and brightness
                        # moonRaDec = self.site.altAzToRaDec(self.site.moonpos(dateTime),lst)
                        # moonDist = raDec.angsep(moonRaDec)

                        _dateTime = datetimeFromJD(time)
                        lst = site.LST_inRads(_dateTime)
                        moonpos = site.moonpos(_dateTime)
                        #check that moon is above horizon!
                        if moonpos.alt > 0.:

                            moonRaDec = site.altAzToRaDec(moonpos,lst)



                            moonBrightness = site.moonphase(_dateTime)*100.
                            s_target = targets[:][nblock]

                            if (radecArray[nblock].angsep(moonRaDec) < s_target[1].minmoonDist) or not (s_target[1].minmoonBright < moonBrightness < s_target[1].maxmoonBright):
                                log.warning('Cannot allocate target due to moon restrictions...')
                                log.debug("Moon Conditions @ %s: Target@ %s | Moon@: %s | AngSep: %.2f (min.: %.2f) |Moon Brightness: %.2f (%.2f:%.2f) "%(time,
                                                                                                           radecArray[nblock],
                                                                                                           moonRaDec,
                                                                                                           radecArray[nblock].angsep(moonRaDec),
                                                                                                        s_target[1].minmoonDist,
                                                                                           moonBrightness,
                                                                                           s_target[1].minmoonBright,
                                                                                           s_target[1].maxmoonBright))
                                break


                        if nightstart <= time < nightend:
                            allocateSlot = np.append(allocateSlot,
                                                     np.array([(time,
                                                                time+blockDuration[nblock]/60./60./24.,
                                                                nballoc_tmp,
                                                                blockidList[nblock],
                                                                True)],
                                                              dtype=slotDtype))
                        else:
                            log.warning("Wrong time stamp. time: %.4f (%.4f/%.4f)"%(time,nightstart,nightend))
                            break
                        nballoc_tmp+=1

                    else:
                        break

                    start = nightstart
                    end = nightend

                    if olst > lstmid:
                        end = midnight+(olst-lstmid)*12./np.pi/24.
                    else:
                        start = midnight-(lstmid-olst)*12./np.pi/24.


                if len(allocateSlot) == nairmass:
                    log.info('Allocating...')
                    obsSlots = np.append(obsSlots,allocateSlot)
                    nalloc+=1
                    nballoc += nballoc_tmp
                else:
                    nballoc_tmp = 0
                    log.debug('Failed...')
                nblock+=1

            if nalloc < nstars:
                log.warning('Could not find enough stars.. Found %i of %i...'%(nalloc,nstars))

            return obsSlots #targets


        return std


def Airmass(alt):

    am = 1./np.cos(np.pi/2.-alt*np.pi/180.)
    if am < 0.:
        am = 999.
    return am
