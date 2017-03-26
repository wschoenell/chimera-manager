
from chimera_manager.controllers.scheduler.algorithms.base import *

class ExtintionMonitor(BaseScheduleAlgorith):

    @staticmethod
    def name():
        return 'STD'

    @staticmethod
    def id():
        return 1

    @staticmethod
    def clean(pid):
        session = Session()

        ext_moni_blocks = session.query(ExtMoniDB).filter(ExtMoniDB.pid == pid)
        for block in ext_moni_blocks:
            for observed_am in block.observed_am:
                session.delete(observed_am)
            session.delete(block)

        session.commit()

    @staticmethod
    def soft_clean(pid,block=None):
        session = Session()

        ext_moni_blocks = session.query(ExtMoniDB).filter(ExtMoniDB.pid == pid)
        for block in ext_moni_blocks:
            for observed_am in block.observed_am:
                session.delete(observed_am)

        session.commit()

    @staticmethod
    def add(block):
        session = Session()

        obsblock = session.merge(block[0])
        # Check if this is already in the database
        ext_moni_block = session.query(ExtMoniDB).filter(ExtMoniDB.pid == obsblock.pid,
                                                         ExtMoniDB.tid == obsblock.objid).first()

        if ext_moni_block is not None:
            # already in the database, just update
            ext_moni_block.nairmass += 1
        else:
            ext_moni_block = ExtMoniDB(pid = obsblock.pid,
                                       tid = obsblock.objid)
            session.add(ext_moni_block)

        session.commit()


    @staticmethod
    def process(*args,**kwargs):
        log = logging.getLogger('sched-algorith(extmoni)')
        log.addHandler(fileHandler)

        slotLen = 60.
        if 'slotLen' in kwargs.keys():
            slotLen = kwargs['slotLen']
        elif len(args) > 1:
            try:
                slotLen = float(args[0])
            except:
                slotLen = 60.

        # Todo: Reject objects that are close to the moon

        # Selecting standard stars is not only searching for the higher in that
        # time but select stars than can be observed at 3 or more (nairmass)
        # different airmasses. It is also important to select stars with
        # different colors (but this will be taken care in the future).

        # Todo: Select by color also

        nightstart = kwargs['obsStart']
        nightend   = kwargs['obsEnd']
        time_grid = np.arange(nightstart,nightend,slotLen/60./60./24.)
        site = kwargs['site']
        targets = kwargs['query']

        nstars = 3 # if 'nstars' not in kwargs else kwargs['nstars']
        nairmass = 3 # if 'nairmass' not in kwargs else kwargs['nairmass']

        overheads = {'autofocus': {'align' : 0., 'set' : 0.},
                     'point': 0.,
                     'readout': 0.,
                     }

        if 'overheads' in kwargs:
            overheads.update(kwargs)

        if 'config' in kwargs:
            config = kwargs['config']
            if 'nstars' in config:
                nstars = config['nstars']

            if 'nairmass' in config:
                nairmass = config['nairmass']

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

            for blk_actions in target[0].actions:
                if blk_actions.__tablename__ == 'action_expose':
                    blockDuration[-1]+=((blk_actions.exptime+overheads['readout'])*blk_actions.frames)
                elif blk_actions.__tablename__ == 'action_focus':
                    if blk_actions.step > 0:
                        blockDuration[-1]+=overheads['autofocus']['align']
                    elif blk_actions.step == 0:
                        blockDuration[-1]+=overheads['autofocus']['set']



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

            # set desired altitudes
            minalt = 90.-np.arccos(1./maxAirmass[nblock])*180./np.pi
            minalt *= 1.1
            desire_alt = np.linspace(minalt,maxAltitude,nairmass)
            # set desired airmasses
            dairMass = 1./np.cos(np.pi/2.-desire_alt*np.pi/180.)# np.linspace(minAM,maxAirmass[nblock]*0.9,nairmass)
            dairMass.sort()
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

            lst_grid = [site.LST_inRads(datetimeFromJD(tt)) for tt in time_grid]
            airmass_grid = np.array([Airmass(float(site.raDecToAltAz(radecArray[nblock],
                                                         lst).alt)) for lst in lst_grid])
            min_amidx = np.argmin(airmass_grid)
            for dam in dairMass:
                converged = False

                # Before culmination
                if airmass_grid[1] < airmass_grid[0]:
                    dam_grid = np.abs(airmass_grid[:min_amidx]-dam)
                    mm = dam_grid < maxAirmass[nblock]
                    log.debug('%s' % dam_grid)
                    dam_grid[mm] = np.max(dam_grid)
                    dam_pos = np.argmin(np.abs(airmass_grid[:min_amidx]-dam))
                    if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                        time = time_grid[dam_pos]
                        converged = True
                    else:
                        dam_pos = np.argmin(np.abs(airmass_grid-dam))
                        mm = dam_grid < maxAirmass[nblock]
                        dam_grid[mm] = np.max(dam_grid)
                        if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                            time = time_grid[dam_pos]
                            converged = True
                else:
                    dam_grid = np.abs(airmass_grid[min_amidx:]-dam)
                    mm = dam_grid < maxAirmass[nblock]
                    log.debug('%s' % dam_grid)
                    dam_grid[mm] = np.max(dam_grid)
                    dam_pos = np.argmin(np.abs(airmass_grid[min_amidx:]-dam))
                    if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                        time = time_grid[dam_pos]
                        converged = True
                    else:
                        dam_pos = np.argmin(np.abs(airmass_grid-dam))
                        mm = dam_grid < maxAirmass[nblock]
                        dam_grid[mm] = np.max(dam_grid)
                        if np.abs(airmass_grid[dam_pos]-dam) < 1e-1:
                            time = time_grid[dam_pos]
                            converged = True

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
                keep_mask = np.zeros_like(time_grid) == 0
                for islot in range(len(obsSlots)):
                    keep_mask = np.bitwise_and(keep_mask,
                                               np.bitwise_not(np.bitwise_and(time_grid > obsSlots['start'][islot],
                                                                             time_grid < obsSlots['end'][islot])
                                                              )
                                                  )
                time_grid = time_grid[keep_mask]
                nalloc+=1
                nballoc += nballoc_tmp
            else:
                nballoc_tmp = 0
                log.debug('Failed...')
            nblock+=1

        if nalloc < nstars:
            log.warning('Could not find enough stars.. Found %i of %i...'%(nalloc,nstars))

        return obsSlots #targets

    @staticmethod
    def next(time, programs):

        log = logging.getLogger('sched-algorith(extmoni.next)')
        log.addHandler(fileHandler)
        log.debug("Selecting target with ExtintionMonitor algorithm.")

        mjd = time #ExtintionMonitor.site.MJD()
        lst = ExtintionMonitor.site.LST(datetimeFromJD(time+2400000.5))

        # dt = np.array([ np.abs(mjd - program[0].slewAt) for program in programs])
        # iprog = np.argmin(dt)

        observe_program = None
        waittime = 1.
        slewAt = mjd

        session = Session()

        for program in programs:
            extmoni_info = session.query(ExtMoniDB).filter(ExtMoniDB.pid == program[0].pid,
                                                           ExtMoniDB.tid == program[0].tid).first()
            target_coord = Position.fromRaDec(Coord.fromH(program[3].targetRa),
                                              Coord.fromD(program[3].targetDec))
            # set desired altitudes
            max_airmass = program[1].maxairmass
            minalt = 90.-np.arccos(1./max_airmass)*180./np.pi
            minalt *= 1.1

            olst = np.float(target_coord.ra.R)*0.999
            maxalt = ExtintionMonitor.site.raDecToAltAz(target_coord, olst).alt.D

            # add 1 to nairmass so the values can be threated as boundaries.
            desire_alt = np.linspace(minalt,maxalt,extmoni_info.nairmass+1)

            # set desired airmasses
            #desire_am = 1./np.cos(np.pi/2.-desire_alt*np.pi/180.)# np.linspace(minAM,maxAirmass[nblock]*0.9,nairmass)
            #desire_am.sort()

            covered = False
            if program[0].slewAt < mjd:
                log.debug("Slew time has passed. Calculating target's current altitude.")

                alt = ExtintionMonitor.site.raDecToAltAz(target_coord,
                                                                  lst).alt.D

                if not (minalt < alt < maxalt):
                    log.debug("Target altitude (%.2f) outside limit (%.2f/%.2f)" % (alt,
                                                                                    minalt,
                                                                                    maxalt))
                    continue

                l = np.where(desire_alt <= alt)[0][-1]
                log.debug("Checking if this altitude position was already covered.")

                for observed_am in extmoni_info.observed_am:
                    lc = np.where(desire_alt <= observed_am.altitude)[0][-1]
                    if l == lc:
                        log.debug("Position already covered, continue.")
                        covered = True
                        break
            else:
                log.debug("Slew still in the future, try to find good time to slew between now and then")
                log.debug('Now: %.4f | Slew@: %.2f | Altitude: min/max: %.2f/%.2f' % (mjd,
                                                                                      program[0].slewAt,
                                                                                      minalt,
                                                                                      maxalt))
                slewAt = program[0].slewAt
                for tt in np.linspace(mjd,program[0].slewAt,10):
                    observe_lst = ExtintionMonitor.site.LST_inRads(datetimeFromJD(tt+2400000.5))
                    alt = ExtintionMonitor.site.raDecToAltAz(target_coord,
                                                             observe_lst).alt.D
                    log.debug('Slew@: %.2f (alt/airmass: %.2f/%.3f )' % (tt, alt,
                                                                         1. / np.cos(np.pi / 2. - alt * np.pi / 180.)))

                    if minalt < alt < maxalt:
                        l = np.where(desire_alt <= alt)[0][-1]
                        log.debug("Check if this altitude position is already covered")
                        covered = False
                        for observed_am in extmoni_info.observed_am:
                            lc = np.where(desire_alt <= observed_am.altitude)[0][-1]
                            if l == lc:
                                log.debug("Position already covered")
                                covered = True
                                break
                            else:
                                log.debug("Position uncovered")
                                covered = False
                                # break

                        if not covered:
                            log.debug("Position uncovered")
                            slewAt = tt
                            break
                        else:
                            log.debug("Position covered. continuing")
                    else:
                        log.debug("Current altitude (%.2f) out of range (%.2f/%.2f)" % (alt,minalt,maxalt))


            if not covered:
                awaittime = slewAt-mjd
                if awaittime < 0.:
                    awaittime = 0.
                if awaittime < waittime:
                    awaittime = waittime
                    observe_program = program
                break
                # session.commit()
                # return program

        if observe_program is not None:
            log.debug("Target ok")
            observe_program[0].slewAt = slewAt
        else:
            log.debug("Could not find suitable target")

        session.commit()
        return observe_program

    @staticmethod
    def observed(time, program, site = None, soft = False):
        mjd = time #ExtintionMonitor.site.MJD()
        if site is None:
            site = ExtintionMonitor.site
        lst = site.LST(datetimeFromJD(time+2400000.5))

        session = Session()
        prog = session.merge(program[0])
        obsblock = session.merge(program[2])
        target = session.merge(program[3])
        extmoni_info = session.query(ExtMoniDB).filter(ExtMoniDB.pid == prog.pid,
                                                       ExtMoniDB.tid == prog.tid).first()
        if extmoni_info is None:
            raise ExtintionMonitorException('Could not find program %s in the database.' % prog.pid)

        target_coord = Position.fromRaDec(Coord.fromH(target.targetRa),
                                          Coord.fromD(target.targetDec))

        alt = site.raDecToAltAz(target_coord,lst).alt.D
        observed_am = ObservedAM(altitude=alt)

        extmoni_info.observed_am.append(observed_am)

        obsblock.observed = True
        # These targets are never completed
        if not soft:
            obsblock.lastObservation = site.ut().replace(tzinfo=None)

        session.commit()
