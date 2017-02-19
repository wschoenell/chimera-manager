import os
import numpy as np
import yaml
from sqlalchemy import or_, and_
import datetime

from chimera_manager.controllers.scheduler.model import ObsBlock, ExtMoniDB, ObservedAM, TimedDB, RecurrentDB, Session
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
        if 'config' in kwargs:
            config = kwargs['config']
            if 'pool_size' in config:
                pool_size = config['pool_size']

            if 'slotLen' in config:
                slotLen = config['slotLen']

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
        from chimera_manager.controllers.scheduler.model import Targets,ObsBlock
        # Filter target by observing data. Leave "NeverObserved" and those observed more than recurrence_time days ago
        today = kwargs['site'].ut().replace(tzinfo=None)
        reference_date = today - datetime.timedelta(days=recurrence_time)

        ntargets = len(kwargs['query'][:])
        # Exclude targets that where observed less then a specified ammount of time
        # kwargs['query'] = kwargs['query'].filter(or_(ObsBlock.observed == False,
        #                                              and_(ObsBlock.observed == True,
        #                                                   ObsBlock.lastObservation < reference_date)))
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

        obstime = site.ut().replace(tzinfo=None) # get time and function entry

        session = Session()
        obsblock = session.merge(program[2])
        obsblock.observed = True

        log.debug('%s: Marking as observed @ %s' % (obsblock.pid, obstime))

        if not soft:
            log.debug('Running in hard mode. Storing main information in database.')
            # prog = session.merge(program[0])
            obsblock.observed = True
            obsblock.lastObservation = site.ut().replace(tzinfo=None)

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


def Airmass(alt):

    am = 1./np.cos(np.pi/2.-alt*np.pi/180.)
    if am < 0.:
        am = 999.
    return am
