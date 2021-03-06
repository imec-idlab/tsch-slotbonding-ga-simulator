#!/usr/bin/python
"""
\brief Model of a 6TiSCH mote.

\author Thomas Watteyne <watteyne@eecs.berkeley.edu>
\author Kazushi Muraoka <k-muraoka@eecs.berkeley.edu>
\author Nicola Accettura <nicola.accettura@eecs.berkeley.edu>
\author Xavier Vilajosana <xvilajosana@eecs.berkeley.edu>
\author Malisa Vucinic <malisa.vucinic@inria.fr>
\author Esteban Municio <esteban.municio@uantwerpen.be>
\author Glenn Daneels <glenn.daneels@uantwerpen.be>
"""

# ============================ logging =========================================

import logging


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


log = logging.getLogger('Mote')
log.setLevel(logging.DEBUG)
log.addHandler(NullHandler())

# ============================ imports =========================================

import copy
import random
import threading
import math

import SimEngine
import SimSettings
import Propagation
import Topology
import eLLSF
import Modulation

# ============================ defines =========================================

# sufficient num. of tx to estimate pdr by ACK
NUM_SUFFICIENT_TX = 10
# maximum number of tx for history
NUM_MAX_HISTORY = 32

DIR_TX = 'TX'
DIR_RX = 'RX'
DIR_TXRX_SHARED = 'SHARED'

DEBUG = 'DEBUG'
INFO = 'INFO'
WARNING = 'WARNING'
ERROR = 'ERROR'

# === app
APP_TYPE_DATA = 'DATA'
APP_TYPE_ACK = 'ACK'  # end to end ACK
APP_TYPE_JOIN = 'JOIN'  # join traffic
APP_TYPE_FRAG = 'FRAG'
RPL_TYPE_DIO = 'DIO'
RPL_TYPE_DAO = 'DAO'
TSCH_TYPE_EB = 'EB'
# === 6top message types
IANA_6TOP_TYPE_REQUEST = '6TOP_REQUEST'
IANA_6TOP_TYPE_RESPONSE = '6TOP_RESPONSE'
IANA_6TOP_TYPE_CONFIRMATION = '6TOP_CONFIRMATION'

# === rpl
RPL_PARENT_SWITCH_THRESHOLD        = 768 # corresponds to 1.5 hops. 6tisch minimal draft use 384 for 2*ETX.
# RPL_PARENT_SWITCH_THRESHOLD = 10768  # corresponds to 1.5 hops. 6tisch minimal draft use 384 for 2*ETX.
# RPL_PARENT_SWITCH_THRESHOLD        = 384 # corresponds to 1.5 hops. 6tisch minimal draft use 384 for 2*ETX.
RPL_MIN_HOP_RANK_INCREASE = 256
RPL_MAX_ETX = 4
RPL_MAX_RANK_INCREASE = RPL_MAX_ETX * RPL_MIN_HOP_RANK_INCREASE * 2  # 4 transmissions allowed for rank increase for parents
RPL_MAX_TOTAL_RANK = 256 * RPL_MIN_HOP_RANK_INCREASE * 2  # 256 transmissions allowed for total path cost for parents
RPL_PARENT_SET_SIZE = 1
DEFAULT_DIO_INTERVAL_MIN = 3  # log2(DIO_INTERVAL_MIN), with DIO_INTERVAL_MIN expressed in ms
DEFAULT_DIO_INTERVAL_DOUBLINGS = 20  # maximum number of doublings of DIO_INTERVAL_MIN (DIO_INTERVAL_MAX = 2^(DEFAULT_DIO_INTERVAL_MIN+DEFAULT_DIO_INTERVAL_DOUBLINGS) ms)
DEFAULT_DIO_REDUNDANCY_CONSTANT = 10  # number of hearings to suppress next transmission in the current interval

# === 6top states
SIX_STATE_IDLE = 0x00
# sending
SIX_STATE_SENDING_REQUEST = 0x01
# waiting for SendDone confirmation
SIX_STATE_WAIT_ADDREQUEST_SENDDONE = 0x02
SIX_STATE_WAIT_DELETEREQUEST_SENDDONE = 0x03
SIX_STATE_WAIT_RELOCATEREQUEST_SENDDONE = 0x04
SIX_STATE_WAIT_COUNTREQUEST_SENDDONE = 0x05
SIX_STATE_WAIT_LISTREQUEST_SENDDONE = 0x06
SIX_STATE_WAIT_CLEARREQUEST_SENDDONE = 0x07
# waiting for response from the neighbor
SIX_STATE_WAIT_ADDRESPONSE = 0x08
SIX_STATE_WAIT_DELETERESPONSE = 0x09
SIX_STATE_WAIT_RELOCATERESPONSE = 0x0a
SIX_STATE_WAIT_COUNTRESPONSE = 0x0b
SIX_STATE_WAIT_LISTRESPONSE = 0x0c
SIX_STATE_WAIT_CLEARRESPONSE = 0x0d
# response
SIX_STATE_REQUEST_ADD_RECEIVED = 0x0e
SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE = 0x0f
SIX_STATE_REQUEST_DELETE_RECEIVED = 0x10
SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE = 0x11

# === 6top commands
IANA_6TOP_CMD_ADD = 0x01  # add one or more cells
IANA_6TOP_CMD_DELETE = 0x02  # delete one or more cells
IANA_6TOP_CMD_RELOCATE = 0x03  # relocate one or more cells
IANA_6TOP_CMD_COUNT = 0x04  # count scheduled cells
IANA_6TOP_CMD_LIST = 0x05  # list the scheduled cells
IANA_6TOP_CMD_CLEAR = 0x06  # clear all cells

# === 6P return code
IANA_6TOP_RC_SUCCESS = 0x00  # operation succeeded
IANA_6TOP_RC_ERROR = 0x01  # generic error
IANA_6TOP_RC_EOL = 0x02  # end of list
IANA_6TOP_RC_RESET = 0x03  # critical error, reset
IANA_6TOP_RC_VER_ERR = 0x04  # unsupported 6P version
IANA_6TOP_RC_SFID_ERR = 0x05  # unsupported SFID
IANA_6TOP_RC_GEN_ERR = 0x06  # wrong schedule generation
IANA_6TOP_RC_BUSY = 0x07  # busy
IANA_6TOP_RC_NORES = 0x08  # not enough resources
IANA_6TOP_RC_CELLLIST_ERR = 0x09  # cellList error

# === MSF
MSF_MIN_NUM_CELLS = 5
MSF_DEFAULT_TIMEOUT_EXP = 1
MSF_MAX_TIMEOUT_EXP = 4
MSF_DEFAULT_SIXTOP_TIMEOUT = 15
MSF_6PTIMEOUT_SEC_FACTOR = 5

MSF_MAX_OLD_PARENT_REMOVAL = 1 # 1 means one retry

# === tsch
TSCH_QUEUE_SIZE = 10
TSCH_MAXTXRETRIES = 4
# TSCH_MIN_BACKOFF_EXPONENT = 1
# TSCH_MAX_BACKOFF_EXPONENT = 1
# === radio
RADIO_MAXDRIFT = 30  # in ppm
# === battery
# see A Realistic Energy Consumption Model for TSCH Networks.
# Xavier Vilajosana, Qin Wang, Fabien Chraim, Thomas Watteyne, Tengfei
# Chang, Kris Pister. IEEE Sensors, Vol. 14, No. 2, February 2014.
CHARGE_Idle_uC = 6.4
CHARGE_TxDataRxAck_uC = 54.5
CHARGE_TxData_uC = 49.5
CHARGE_RxDataTxAck_uC = 32.6
CHARGE_RxData_uC = 22.6
CHARGE_IdleNotSync_uC = 45.0

# === 6LoWPAN Reassembly
SIXLOWPAN_DEFAULT_MAX_REASS_QUEUE_NUM = 1
# === Fragment Forwarding
FRAGMENT_FORWARDING_DEFAULT_MAX_VRB_ENTRY_NUM = 50

BROADCAST_ADDRESS = 0xffff


# ============================ body ============================================

class Mote(object):

    def __init__(self, id):
        # store params
        self.id = id
        # local variables
        self.dataLock = threading.RLock()

        self.engine = SimEngine.SimEngine()
        self.settings = SimSettings.SimSettings()

        self.genMSF = random.Random()
        self.genMSF.seed(self.settings.seed + self.id)
        self.geneLLSF = random.Random()
        self.geneLLSF.seed(self.settings.seed + self.id)

        self.genSporadic = random.Random()
        self.genSporadic.seed(self.settings.seed + self.id)

        self.genMobility = random.Random()
        self.genMobility.seed(self.settings.seed + self.id)

        self.genEBDIO = random.Random()
        self.genEBDIO.seed(self.settings.seed + self.id)

        # random.seed(self.settings.seed + self.id)

        self.propagation = Propagation.Propagation()

        # join process
        self.isJoined = False
        self.joinRetransmissionPayload = 0
        self.joinAsn = 0  # ASN at the time node successfully joined
        self.firstBeaconAsn = 0
        # app
        self.lastRandom = 0
        self.pkPeriod = self.settings.pkPeriod
        self.reassQueue = {}
        self.vrbTable = {}
        self.next_datagram_tag = self.genEBDIO.randint(0, 2 ** 16 - 1)
        # role
        self.dagRoot = False
        # rpl
        self.rank = None
        self.dagRank = None
        self.parentSet = []
        self.oldPreferredParent = None  # preserve old preferred parent upon a change
        self.preferredParent = None
        self.rplRxDIO = {}  # indexed by neighbor, contains int
        self.neighborRank = {}  # indexed by neighbor
        self.neighborDagRank = {}  # indexed by neighbor
        self.dagRootAddress = None

        self.childrenRPL = []

        # MSF
        self.numCellsElapsed = 0
        self.numCellsUsed = 0
        # 6top
        self.numCellsToNeighbors = {}  # indexed by neighbor, contains int
        self.numCellsFromNeighbors = {}  # indexed by neighbor, contains int

        self.isConverged = False  # is converged, can mean different things for different SFs
        self.isConvergedASN = None

        self.closestNeighbor = None

        # 6top protocol
        self.sixtopStates = {}
        # a dictionary that stores the different 6p states for each neighbor
        # in each entry the key is the neighbor.id
        # the values are:
        #                 'state', used for tracking the transaction state for each neighbor
        #                 'responseCode', used in the receiver node to act differently when a responseACK is received
        #                 'blockedCells', candidates cell pending for an operation

        # tsch
        self.txQueue = []
        self.pktToSend = None
        self.schedule = {}  # indexed by ts, contains cell
        self.waitingFor = None
        self.timeCorrectedSlot = None
        self.isSync = False
        self.firstEB = True  # flag to indicate first received enhanced beacon
        self._tsch_resetBroadcastBackoff()
        self.backoffPerNeigh = {}
        self.backoffExponentPerNeigh = {}
        # radio
        self.txPower = 10.0  # dBm
        self.antennaGain = 0  # dBi
        self.minRssi = self.settings.minRssi  # dBm
        self.noisepower = -105  # dBm
        self.drift = self.genEBDIO.uniform(-RADIO_MAXDRIFT, RADIO_MAXDRIFT)
        # wireless
        self.RSSI = {}  # indexed by neighbor
        self.PDR = {}  # indexed by neighbor
        self.initialRSSI = {}
        self.initialPDR = {}
        # location
        # battery
        self.chargeConsumed = 0
        self.nrIdle = 0
        self.nrIdleNotSync = 0
        self.nrSleep = 0
        self.nrTxDataRxAck = 0
        self.nrTxDataRxNack = 0
        self.nrTxData = 0
        self.nrTxDataNoAck = 0
        self.nrRxDataTxAck = 0
        self.nrRxData = 0
        self.consumption = { 'nrIdle': {}, 'nrIdleNotSync': {}, 'nrSleep': {}, 'nrTxDataRxAck': {}, 'nrTxDataRxNack': {}, 'nrTxData': {}, 'nrTxDataNoAck': {}, 'nrTxDataNoAck': {}, 'nrRxDataTxAck': {}, 'nrRxData': {}}
        self.totalIdle = 0
        self.totalIdleNotSync = 0
        self.totalSleep = 0
        self.totalTxDataRxAck = 0
        self.totalTxDataRxNack = 0
        self.totalTxData = 0
        self.totalTxDataNoAck = 0
        self.totalRxDataTxAck = 0
        self.totalRxData = 0
        self.totalConsumption = { 'nrIdle': {}, 'nrIdleNotSync': {}, 'nrSleep': {}, 'nrTxDataRxAck': {}, 'nrTxDataRxNack': {}, 'nrTxData': {}, 'nrTxDataNoAck': {}, 'nrTxDataNoAck': {}, 'nrRxDataTxAck': {}, 'nrRxData': {}}
        self.nrRemovedCells = 0
        self.nrNoTxDataRxAck = []
        # reassembly/fragmentation
        if not hasattr(self.settings, 'numReassQueue'):
            self.maxReassQueueNum = SIXLOWPAN_DEFAULT_MAX_REASS_QUEUE_NUM
        else:
            self.maxReassQueueNum = self.settings.numReassQueue
        if hasattr(self.settings, 'maxVRBEntryNum') and self.settings.maxVRBEntryNum > 0:
            self.maxVRBEntryNum = self.settings.maxVRBEntryNum
        else:
            self.maxVRBEntryNum = FRAGMENT_FORWARDING_DEFAULT_MAX_VRB_ENTRY_NUM
        # stats
        self._stats_resetMoteStats()
        self._stats_resetQueueStats()
        self._stats_resetLatencyStats()
        self._stats_resetHopsStats()
        self._stats_resetRadioStats()

        self.arrivedToGen = 0
        self.notGenerated = 0
        self.pktGen = 0  # DATA packets generated during the experiment (without warming up)
        self.pktReceived = 0  # DATA packets received during the experiment (without warming up)
        self.pktDropMac = 0  # DATA packets drop during the experiment (without warming up) due to MAC retransmissions
        self.pktDropQueue = 0  # DATA packets received during the experiment (without warming up) to Queue full

        self.tsSixTopReqRecv = {}  # for every neighbor, it tracks the 6top transaction latency
        self.avgsixtopLatency = []  # it tracks the average 6P transaction latency in a given frame
        
        self.rplPrefParentChurns = 0
        self.rplPrefParentChurnToAndASN = (None, None)
        self.rplPrefParentASNDiffs = []
        self.oldPrefParentRemoval = 0
        self.currentOldPrefParentRemoval = 0

        self.startApp = None
        self.periodApp = None

        self.prevX = 0.0
        self.prevY = 0.0

        self.repVec = (None, None)
        self.attVec = (None, None)
        self.resVec = (None, None)

        self.sixtopTxAddReq = 0
        self.sixtopTxDelReq = 0
        self.sixtopTxAddResp = 0
        self.sixtopTxDelResp = 0
        
        self.activeDAO = 0
        self.initiatedDAO = 0
        self.receivedDAO = 0

        self.datapkts = 0
        self.requestspkts = 0
        self.responsespkts = 0
        self.othertypes = []

        self.broadcastpackets = []

        self.sporadic = None
        self.sporadicStart = None

        self.modulation = {} # indexed by neighbor

        self.totalPropagationData = 0
        self.successPropagationData = 0
        self.allInterferers = []
        self.hadInterferers = 0
        self.interferenceFailures = 0
        self.interferenceLockFailures = 0
        self.signalFailures = 0

        self.aggregatedSlot = dict()
        self.onGoingReception = False

        self.distanceTo = dict()

        # in case of slot bonding
        self.allocatedBondedSlots = 0

        self.eLLSF = None
        if self.settings.sf == 'ellsf':
            self.eLLSF = eLLSF.eLLSF(self)
            self.eLLSF.ELLSF_TIMESLOTS = range(self.settings.nrMinimalCells, 101)
        elif self.settings.sf == 'msf':
            pass
        elif self.settings.sf == 'ilp':
            self.settings.disableMSF = True
        else:
            assert False

    # ======================== stack ===========================================

    # ===== role

    def role_setDagRoot(self):
        self.dagRoot = True
        self.rank = 0
        self.dagRank = 0
        self.packetLatencies = []  # in slots
        self.packetHops = []
        self.parents = {}  # dictionary containing parents of each node from whom DAG root received a DAO
        self.isJoined = True
        self.isSync = True
        self.isConverged = True
        self.isConvergedASN = None

        self.pktLatencies = {}  # DATA latencies for pkts (possibly after convergence), per neighbor

        # imprint DAG root's ID at each mote
        for mote in self.engine.motes:
            mote.dagRootAddress = self

    # ===== join process

    def join_scheduleJoinProcess(self):
        delay = self.settings.slotDuration + self.settings.joinAttemptTimeout * self.genEBDIO.random()

        # schedule
        self.engine.scheduleIn(
            delay=delay,
            cb=self.join_initiateJoinProcess,
            uniqueTag=(self.id, '_join_action_initiateJoinProcess'),
            priority=2,
        )

    def join_setJoined(self):

        assert not self.dagRoot

        if not self.isJoined:
            self.isJoined = True
            self.joinAsn = self.engine.getAsn()
            # log
            self._log(
                INFO,
                "[join] Mote joined",
            )

            # schedule MSF bootstrap of the preferred parent
            if _msf_is_enabled():
                self._msf_schedule_parent_change()

            # check if all motes have joined, if so end the simulation after numCyclesPerRun
            if self.settings.withJoin and all(mote.isJoined == True for mote in self.engine.motes):
                if self.settings.numCyclesPerRun != 0:
                    # experiment time in ASNs
                    simTime = self.settings.numCyclesPerRun * self.settings.slotframeLength
                    # offset until the end of the current cycle
                    offset = self.settings.slotframeLength - (self.engine.asn % self.settings.slotframeLength)
                    # experiment time + offset
                    delay = simTime + offset
                else:
                    # simulation will finish in the next asn
                    delay = 1
                # end the simulation
                self.engine.terminateSimulation(delay)

    def join_initiateJoinProcess(self):
        if not self.dagRoot:
            if self.preferredParent:
                if not self.isJoined:
                    self.join_sendJoinPacket(token=self.settings.joinNumExchanges - 1, destination=self.dagRootAddress)
            else:  # node doesn't have a parent yet, re-scheduling
                self.join_scheduleJoinProcess()

    def join_sendJoinPacket(self, token, destination):
        # send join packet with payload equal to the number of exchanges
        # create new packet
        sourceRoute = []
        if self.dagRoot:
            sourceRoute = self._rpl_getSourceRoute([destination.id])

        if sourceRoute or not self.dagRoot:
            # create new packet
            newPacket = {
                'asn': self.engine.getAsn(),
                'type': APP_TYPE_JOIN,
                'code': None,
                'payload': [token, self.id if not self.dagRoot else None,
                            self.preferredParent.id if not self.dagRoot else None],
                'retriesLeft': TSCH_MAXTXRETRIES,
                'srcIp': self,  # DAG root
                'dstIp': destination,
                'sourceRoute': sourceRoute
            }

            # enqueue packet in TSCH queue
            isEnqueued = self._tsch_enqueue(newPacket)

            if isEnqueued:
                # increment traffic
                self._log(INFO, "[join] Enqueued join packet for mote {0} with token = {1}", (destination.id, token))
            else:
                # update mote stats
                self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

            # save last token sent
            self.joinRetransmissionPayload = token

            # schedule retransmission
            if not self.dagRoot:
                self.engine.scheduleIn(
                    delay=self.settings.slotDuration + self.settings.joinAttemptTimeout,
                    cb=self.join_retransmitJoinPacket,
                    uniqueTag=(self.id, '_join_action_retransmission'),
                    priority=2,
                )

    def join_retransmitJoinPacket(self):
        if not self.dagRoot and not self.isJoined:
            self.join_sendJoinPacket(self.joinRetransmissionPayload, self.dagRootAddress)

    def join_receiveJoinPacket(self, srcIp, payload, timestamp):
        self.engine.removeEvent((self.id, '_join_action_retransmission'))  # remove the pending retransmission event

        self._log(INFO, "[join] Received join packet from {0} with token {1}", (srcIp.id, payload[0]))

        # this is a hack to allow downward routing of join packets before node has sent a DAO
        if self.dagRoot:
            self.parents.update({tuple([payload[1]]): [[payload[2]]]})

        if payload[0] != 0:
            newToken = payload[0] - 1
            self.join_sendJoinPacket(token=newToken, destination=srcIp)
        else:
            self.join_setJoined()
            # Trigger sending EBs and DIOs, and the rest of the stack
            self._init_stack()

    def join_joinedNeighbors(self):
        return [nei for nei in self._myNeighbors() if nei.isJoined == True]

    # def print_random(self):
    #     self._log(
    #         INFO,
    #         "[random] Mote joined: {0}",
    #         (self.genEBDIO.random(),)
    #     )

    # ===== application

    def _app_schedule_sendSinglePacket(self, firstPacket=False):
        """
        create an event that is inserted into the simulator engine to send the data according to the traffic
        """

        if self.pkPeriod == 0:
            # disable sending packet
            return

        # if not firstPacket:
        #     # compute random delay
        #     delay = self.pkPeriod * (1 + random.uniform(-self.settings.pkPeriodVar, self.settings.pkPeriodVar))
        # else:
        #     # compute initial time within the range of [next asn, next asn+pkPeriod]
        #     delay = self.settings.slotDuration + self.pkPeriod * random.random()

        delay = self.pkPeriod * (1 + random.uniform(-self.settings.pkPeriodVar, self.settings.pkPeriodVar))
        # delay = self.settings.slotframeLength * self.settings.slotDuration
        assert delay > 0
        # delayASN = int(self.engine.asn + (float(delay) / float(self.settings.slotDuration)))
        
        # extraRandom = random.randint(0, 9)
        # delayASN -= self.lastRandom
        # delayASN += extraRandom
        # # 
        # # exit()
        # 
        # 
        # while delayASN <= self.engine.asn:
        #     delay = self.pkPeriod * (1 + random.uniform(-self.settings.pkPeriodVar, self.settings.pkPeriodVar))
        #     extraRandom = random.randint(0, self.pkPeriod - 9)
        #     delay -= self.lastRandom
        #     delay += extraRandom
        #     delayASN = int(self.engine.asn + (float(delay) / float(self.settings.slotDuration)))

        # self.lastRandom = extraRandom
        # 
        # self.engine.scheduleAtAsn(
        #     asn=delayASN,
        #     cb=self._app_action_sendSinglePacket,
        #     uniqueTag=(self.id, '_app_action_sendSinglePacket'),
        #     priority=2,
        # )

        # schedule
        self.engine.scheduleIn(
            delay=delay,
            cb=self._app_action_sendSinglePacket,
            uniqueTag=(self.id, '_app_action_sendSinglePacket'),
            priority=2,
        )

    def _app_schedule_sendSporadicPacket(self, firstPacket=False):
        """
        create an event that is inserted into the simulator engine to send the data according to the traffic
        """

        if self.pkPeriod == 0:
            # disable sending packet
            return

        sporadics = [4000, 6000, 8000]
        self.sporadic = sporadics[self.genSporadic.randint(0, len(sporadics) - 1)] * float(self.settings.slotDuration)
        # log.info("Mote {0}, sporadic sending = {1}.".format(self.id, self.sporadic))
        delay = int(self.sporadic * (1 + self.genSporadic.uniform(-0.03, 0.03)))

        assert delay > 0

        # schedule
        self.engine.scheduleIn(
            delay=delay,
            cb=self._app_action_sendSporadicPacket,
            uniqueTag=(self.id, '_app_action_sendSporadicPacket'),
            priority=2,
        )

    def _app_schedule_sendPacketBurst(self):
        """ create an event that is inserted into the simulator engine to send a data burst"""

        # schedule numPacketsBurst packets at burstTimestamp
        for i in xrange(self.settings.numPacketsBurst):
            self.engine.scheduleIn(
                delay=self.settings.burstTimestamp,
                cb=self._app_action_enqueueData,
                uniqueTag=(self.id, '_app_action_enqueueData_burst1_{0}'.format(i)),
                priority=2,
            )
            self.engine.scheduleIn(
                delay=3 * self.settings.burstTimestamp,
                cb=self._app_action_enqueueData,
                uniqueTag=(self.id, '_app_action_enqueueData_burst2_{0}'.format(i)),
                priority=2,
            )

    def _app_action_sendSinglePacket(self):
        """ actual send data function. Evaluates queue length too """

        # print 'txQueue filled with %d packets' % len(self.txQueue)
        # print 'Sending APP packet at ts %d and at ASN %d' % (self.engine.asn % self.settings.slotframeLength, self.engine.asn)

        # enqueue data
        self._app_action_enqueueData()

        # schedule next _app_action_sendSinglePacket
        self._app_schedule_sendSinglePacket()

    def _app_action_sendSporadicPacket(self):
        """ actual send data function. Evaluates queue length too """

        # enqueue data
        self._app_action_enqueueSporadicData()

        # schedule next _app_schedule_sendSporadicPacket
        self._app_schedule_sendSporadicPacket()

    def _app_action_receiveAck(self, srcIp, payload, timestamp):
        assert not self.dagRoot

    def _app_action_receivePacket(self, srcIp, payload, timestamp):
        assert self.dagRoot

        # update mote stats
        if self.settings.convergeFirst and payload[1] >= self.engine.asnInitExperiment and payload[1] <= self.engine.asnEndExperiment:
            self.pktReceived += 1
            if srcIp.id not in self.pktLatencies:
                self.pktLatencies[srcIp.id] = []
            # print 'timestamp = {0} - payload {1}'.format(timestamp, payload[1])
            # print 'timestamp = {0} - payload {1}'.format(timestamp % self.settings.slotframeLength, payload[1] % self.settings.slotframeLength)
            self.pktLatencies[srcIp.id].append(timestamp - payload[1])
        elif not self.settings.convergeFirst:
            self.pktReceived += 1
            if srcIp.id not in self.pktLatencies:
                self.pktLatencies[srcIp.id] = []
            self.pktLatencies[srcIp.id].append(timestamp - payload[1])
        self._stats_incrementMoteStats('appReachesDagroot')

        # print 'At root, received packet at ts = %d and ASN = %d with latency = %.4f' % (self.engine.asn % self.settings.slotframeLength, self.engine.asn, timestamp - payload[1])
        # if timestamp - payload[1] == 33:
        # assert False
        # assert False

        # calculate end-to-end latency
        self._stats_logLatencyStat(timestamp - payload[1])

        # log the number of hops
        self._stats_logHopsStat(payload[2])

        # print 'Received DATA packet on mote %d at ts %d with latency %d' % (self.id, self.engine.asn % self.settings.slotframeLength, timestamp - payload[1])

        # assert False

        if self.settings.downwardAcks:  # Downward End-to-end ACKs
            destination = srcIp

            sourceRoute = self._rpl_getSourceRoute([destination.id])

            if sourceRoute:  # if DAO was received from this node

                # send an ACK
                # create new packet
                newPacket = {
                    'asn': self.engine.getAsn(),
                    'type': APP_TYPE_ACK,
                    'code': None,
                    'payload': [],
                    'retriesLeft': TSCH_MAXTXRETRIES,
                    'srcIp': self,  # DAG root
                    'dstIp': destination,
                    'sourceRoute': sourceRoute

                }

                # enqueue packet in TSCH queue
                if not self._tsch_enqueue(newPacket):
                    self._radio_drop_packet(newPacket, 'droppedAppAckFailedEnqueue')

    def _app_action_enqueueData(self):
        """ enqueue data packet into stack """

        assert not self.dagRoot

        self._log(
            INFO,
            "[app] Trying to enqueue a DATA packet to {0}.",
            (self.preferredParent.id,),
        )

        if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
            self.arrivedToGen += 1  # stat that is not resetted
        elif not self.settings.convergeFirst:
            self.arrivedToGen += 1

        if self.preferredParent and \
                (self.settings.sf == 'ilp' or (self.settings.sf != 'ilp' and self.numCellsToNeighbors.get(self.preferredParent, 0) != 0)):
            # if the SF is the ILP, you can actually have NO cell and stil generate a packet. It will be dropped.

            # create new packet
            newPacket = {
                'asn': self.engine.getAsn(),
                'type': APP_TYPE_DATA,
                'code': None,
                'payload': [self.id, self.engine.getAsn(), 1],
            # the payload is used for latency and number of hops calculation
                'retriesLeft': TSCH_MAXTXRETRIES,
                'srcIp': self,
                'dstIp': self.dagRootAddress,
                'sourceRoute': [],
            }

            # update mote stats
            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.pktGen += 1  # stat that is not resetted
            elif not self.settings.convergeFirst:
                self.pktGen += 1
            self._stats_incrementMoteStats('appGenerated')

            # enqueue packet in TSCH queue
            if hasattr(self.settings, 'numFragments') and self.settings.numFragments > 1:
                self._app_frag_packet(newPacket)
            else:
                # send it as a single frame
                isEnqueued = self._tsch_enqueue(newPacket)
                if isEnqueued:
                    self._log(
                        INFO,
                        "[app] DATA packet enqueued (len queue: {0}, shared cells to pref: {1}).",
                        (len(self.txQueue), len(self.getSharedCells(self.preferredParent))),
                    )
                    pass
                else:
                    # update mote stats
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.pktDropQueue += 1
                    elif not self.settings.convergeFirst:
                        self.pktDropQueue += 1
                    self._radio_drop_packet(newPacket, 'droppedDataFailedEnqueue')
                    self._log(
                        INFO,
                        "[app] DATA packet dropped. (queue length {0}, {1})",
                        (len(self.txQueue), str(self.txQueue)),
                    )
        else:
            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.notGenerated += 1  # stat that is not resetted
            elif not self.settings.convergeFirst:
                self.notGenerated += 1

    def _app_action_enqueueSporadicData(self):
        """ enqueue data packet into stack """

        assert not self.dagRoot

        self._log(
            INFO,
            "[app] Trying to enqueue a SPORADIC DATA packet to {0}.",
            (self.preferredParent.id,),
        )

        if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
            self.arrivedToGen += 1  # stat that is not resetted
        elif not self.settings.convergeFirst:
            self.arrivedToGen += 1

        if self.preferredParent and self.numCellsToNeighbors.get(self.preferredParent, 0) != 0:

            # create new packet
            newPacket = {
                'asn': self.engine.getAsn(),
                'type': APP_TYPE_DATA,
                'code': None,
                'payload': [self.id, self.engine.getAsn(), 1],
            # the payload is used for latency and number of hops calculation
                'retriesLeft': TSCH_MAXTXRETRIES,
                'srcIp': self,
                'dstIp': self.dagRootAddress,
                'sourceRoute': [],
            }

            # update mote stats
            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.pktGen += 1  # stat that is not resetted
            elif not self.settings.convergeFirst:
                self.pktGen += 1
            self._stats_incrementMoteStats('appGenerated')

            # enqueue packet in TSCH queue
            if hasattr(self.settings, 'numFragments') and self.settings.numFragments > 1:
                self._app_frag_packet(newPacket)
            else:
                # send it as a single frame
                isEnqueued = self._tsch_enqueue(newPacket)
                if isEnqueued:
                    self._log(
                        INFO,
                        "[app] SPORADIC DATA packet enqueued (len queue: {0}, shared cells to pref: {1}).",
                        (len(self.txQueue), len(self.getSharedCells(self.preferredParent))),
                    )
                    pass
                else:
                    # update mote stats
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.pktDropQueue += 1
                    elif not self.settings.convergeFirst:
                        self.pktDropQueue += 1
                    self._radio_drop_packet(newPacket, 'droppedDataFailedEnqueue')
                    self._log(
                        INFO,
                        "[app] SPORADIC DATA packet dropped. (queue length {0}, {1})",
                        (len(self.txQueue), str(self.txQueue)),
                    )
        else:
            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.notGenerated += 1  # stat that is not resetted
            elif not self.settings.convergeFirst:
                self.notGenerated += 1


    def _app_is_frag_to_forward(self, frag):

        smac = frag['smac']
        dstIp = frag['dstIp']
        size = frag['payload'][3]['datagram_size']
        itag = frag['payload'][3]['datagram_tag']
        offset = frag['payload'][3]['datagram_offset']
        entry_lifetime = 60 / self.settings.slotDuration

        for mac in self.vrbTable.keys():
            for tag in self.vrbTable[mac].keys():
                if (self.engine.getAsn() - self.vrbTable[mac][tag]['ts']) > entry_lifetime:
                    del self.vrbTable[mac][tag]
            if len(self.vrbTable[mac]) == 0:
                del self.vrbTable[mac]

        if offset == 0:
            vrb_entry_num = 0
            for i in self.vrbTable:
                vrb_entry_num += len(self.vrbTable[i])

            if (not self.dagRoot) and (vrb_entry_num == self.maxVRBEntryNum):
                # no room for a new entry
                self._radio_drop_packet(frag, 'droppedFragVRBTableFull')
                return False

            if smac not in self.vrbTable:
                self.vrbTable[smac] = {}

            # In our design, vrbTable has (in-smac, in-tag, nexthop,
            # out-tag). However, it doesn't have nexthop mac address since
            # nexthop is determined at TSCH layer in this simulation.
            if itag in self.vrbTable[smac]:
                # duplicate first fragment
                frag['dstIp'] = None  # this frame will be dropped by the caller
                return False
            else:
                self.vrbTable[smac][itag] = {}

            if dstIp == self:
                # this is a special entry for fragments destined to the mote
                self.vrbTable[smac][itag]['otag'] = None
            else:
                self.vrbTable[smac][itag]['otag'] = self.next_datagram_tag
                self.next_datagram_tag = (self.next_datagram_tag + 1) % 65536
            self.vrbTable[smac][itag]['ts'] = self.engine.getAsn()

            if (hasattr(self.settings, 'optFragmentForwarding') and
                    (self.settings.optFragmentForwarding is not None) and
                    'kill_entry_by_missing' in self.settings.optFragmentForwarding):
                self.vrbTable[smac][itag]['next_offset'] = 0

        if smac in self.vrbTable and itag in self.vrbTable[smac]:
            if self.vrbTable[smac][itag]['otag'] == None:
                return False  # this is for us, which needs to be reassembled

            if (hasattr(self.settings, 'optFragmentForwarding') and
                    (self.settings.optFragmentForwarding is not None) and
                    'kill_entry_by_missing' in self.settings.optFragmentForwarding):
                if offset == self.vrbTable[smac][itag]['next_offset']:
                    self.vrbTable[smac][itag]['next_offset'] += 1
                else:
                    del self.vrbTable[smac][itag]
                    self._radio_drop_packet(frag, 'droppedFragMissingFrag')
                    return False

            frag['asn'] = self.engine.getAsn()
            frag['payload'][2] += 1  # update the number of hops
            frag['payload'][3]['datagram_tag'] = self.vrbTable[smac][itag]['otag']
        else:
            self._radio_drop_packet(frag, 'droppedFragNoVRBEntry')
            return False

        # return True when the fragment is to be forwarded even if it cannot be
        # forwarded due to out-of-order or full of queue
        if (hasattr(self.settings, 'optFragmentForwarding') and
                'kill_entry_by_last' in self.settings.optFragmentForwarding and
                offset == (self.settings.numFragments - 1)):
            # this fragment is the last one
            del self.vrbTable[smac][itag]

        return True

    def _app_frag_packet(self, packet):

        # fragment packet into the specified number of pieces
        tag = self.next_datagram_tag
        self.next_datagram_tag = (self.next_datagram_tag + 1) % 65536
        for i in range(0, self.settings.numFragments):
            frag = copy.copy(packet)
            frag['type'] = APP_TYPE_FRAG
            frag['payload'] = copy.deepcopy(packet['payload'])
            frag['payload'].append({'datagram_size': self.settings.numFragments,
                                    'datagram_tag': tag,
                                    'datagram_offset': i})
            frag['sourceRoute'] = copy.deepcopy(packet['sourceRoute'])
            if not self._tsch_enqueue(frag):
                # we may want to stop fragmentation here. but just continue it
                # for simplicity
                self._radio_drop_packet(frag, 'droppedFragFailedEnqueue')

    def _app_reass_packet(self, smac, payload):
        size = payload[3]['datagram_size']
        tag = payload[3]['datagram_tag']
        offset = payload[3]['datagram_offset']
        reass_queue_lifetime = 60 / self.settings.slotDuration

        if len(self.reassQueue) > 0:
            # remove expired entry
            for s in list(self.reassQueue):
                for t in list(self.reassQueue[s]):
                    if (self.engine.getAsn() - self.reassQueue[s][t]['ts']) > reass_queue_lifetime:
                        del self.reassQueue[s][t]
                    if len(self.reassQueue[s]) == 0:
                        del self.reassQueue[s]

        if size > self.settings.numFragments:
            # the size of reassQueue is the same number as self.settings.numFragments.
            # larger packet than reassQueue should be dropped.
            self._radio_drop_packet({'payload': payload}, 'droppedFragTooBigForReassQueue')
            return False

        if (smac not in self.reassQueue) or (tag not in self.reassQueue[smac]):
            if not self.dagRoot:
                reass_queue_num = 0
                for i in self.reassQueue:
                    reass_queue_num += len(self.reassQueue[i])
                if reass_queue_num == self.maxReassQueueNum:
                    # no room for a new entry
                    self._radio_drop_packet({'payload': payload}, 'droppedFragReassQueueFull')
                    return False
            else:
                pass

        if smac not in self.reassQueue:
            self.reassQueue[smac] = {}
        if tag not in self.reassQueue[smac]:
            self.reassQueue[smac][tag] = {'ts': self.engine.getAsn(), 'fragments': []}

        if offset not in self.reassQueue[smac][tag]['fragments']:
            self.reassQueue[smac][tag]['fragments'].append(offset)
        else:
            # it's a duplicate fragment or queue overflow
            return False

        if size == len(self.reassQueue[smac][tag]['fragments']):
            del self.reassQueue[smac][tag]
            if len(self.reassQueue[smac]) == 0:
                del self.reassQueue[smac]
            return True

        return False

    def _tsch_action_enqueueEB(self):
        """ enqueue EB packet into stack """

        if self.dagRoot or (self.preferredParent and \
                            (self.settings.sf == 'ilp' or (self.settings.sf != 'ilp' and self.numCellsToNeighbors.get(self.preferredParent, 0) != 0))):
            # for the ILP, you can have no cells to your parent and still enqueue. It will be dropped.

            # create new packet
            newPacket = {
                'asn': self.engine.getAsn(),
                'type': TSCH_TYPE_EB,
                'code': None,
                'payload': [self.dagRank],  # the payload is the rpl rank
                'retriesLeft': 1,  # do not retransmit broadcast
                'srcIp': self,
                'dstIp': BROADCAST_ADDRESS,
                'sourceRoute': []
            }

            # enqueue packet in TSCH queue
            if not self._tsch_enqueue(newPacket):
                # update mote stats
                self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

    def _tsch_schedule_sendEB(self, firstEB=False):

        if (not hasattr(self.settings, 'beaconPeriod')) or (self.settings.beaconPeriod == 0):
            # disable periodic EB transmission
            return

        with self.dataLock:

            asn = self.engine.getAsn()

            if self.settings.bayesianBroadcast:
                futureAsn = int(self.settings.slotframeLength)
            else:
                futureAsn = int(math.ceil(
                    self.genEBDIO.uniform(0.8 * self.settings.beaconPeriod, 1.2 * self.settings.beaconPeriod) / (
                        self.settings.slotDuration)))

            # schedule at start of next cycle
            self.engine.scheduleAtAsn(
                asn=asn + futureAsn,
                cb=self._tsch_action_sendEB,
                uniqueTag=(self.id, '_tsch_action_sendEB'),
                priority=3,
            )

    def _tsch_action_sendEB(self):

        with self.dataLock:
            self._log(
                INFO,
                'Send EB.',
            )

            if self.settings.bayesianBroadcast:
                beaconProb = float(self.settings.beaconProbability) / float(len(self.join_joinedNeighbors())) if len(
                    self.join_joinedNeighbors()) else float(self.settings.beaconProbability)
                sendBeacon = True if self.genEBDIO.random() < beaconProb else False
            else:
                sendBeacon = True
            if self.preferredParent or self.dagRoot:
                if self.isJoined or not self.settings.withJoin:
                    if sendBeacon:
                        self._tsch_action_enqueueEB()
                        self._stats_incrementMoteStats('tschTxEB')

            self._tsch_schedule_sendEB()  # schedule next EB

    def _tsch_action_receiveEB(self, type, smac, payload):

        if self.dagRoot:
            return

        # got an EB, increment stats
        self._stats_incrementMoteStats('tschRxEB')
        if self.firstEB and not self.isSync:
            assert self.settings.withJoin
            # log
            self._log(
                INFO,
                "[tsch] synced on EB received from mote {0}.",
                (smac.id,),
            )
            self.firstBeaconAsn = self.engine.getAsn()
            self.firstEB = False
            # declare as synced to the network
            self.isSync = True
            # set neighbors variables before starting request cells to the preferred parent
            # for m in self._myNeighbors():
            #     self._tsch_resetBackoffPerNeigh(m)
            for m in self.engine.motes:
                if m.id != self.id:
                    self._tsch_resetBackoffPerNeigh(m)

            # add the minimal cell to the schedule
            self._tsch_add_minimal_cell()
            # trigger join process
            self.join_scheduleJoinProcess()  # trigger the join process

    # ===== rpl

    def _rpl_action_enqueueDIO(self):
        """ enqueue DIO packet into stack """
        if self.settings.minCellsMSF >= 1:
            if self.dagRoot \
                    or (self.preferredParent and \
                        (self.settings.sf == 'ilp' or (self.settings.sf != 'ilp' and self.numCellsToNeighbors.get(self.preferredParent, 0) != 0))):
                # for the ILP SF, you can have no cells to your parent and still enqueue. It will be dropped.
            # if self.dagRoot or self.preferredParent:

                self._stats_incrementMoteStats('rplTxDIO')

                # create new packet
                newPacket = {
                    'asn': self.engine.getAsn(),
                    'type': RPL_TYPE_DIO,
                    'code': None,
                    'payload': [self.rank],  # the payload is the rpl rank
                    'retriesLeft': 1,  # do not retransmit broadcast
                    'srcIp': self,
                    'dstIp': BROADCAST_ADDRESS,
                    'sourceRoute': []
                }
                # enqueue packet in TSCH queue
                if not self._tsch_enqueue(newPacket):
                    # update mote stats
                    self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')
        else:
            if self.dagRoot or self.preferredParent:

                self._stats_incrementMoteStats('rplTxDIO')

                # create new packet
                newPacket = {
                    'asn': self.engine.getAsn(),
                    'type': RPL_TYPE_DIO,
                    'code': None,
                    'payload': [self.rank],  # the payload is the rpl rank
                    'retriesLeft': 1,  # do not retransmit broadcast
                    'srcIp': self,
                    'dstIp': BROADCAST_ADDRESS,
                    'sourceRoute': []
                }

                # enqueue packet in TSCH queue
                if not self._tsch_enqueue(newPacket):
                    # update mote stats
                    self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

    def _rpl_action_enqueueDAO(self):
        """ enqueue DAO packet into stack """

        assert not self.dagRoot

        # only start sending DAOs if: I have a preferred parent AND dedicated cells to that parent
        if self.preferredParent and (self.settings.sf == 'ilp' or (self.settings.sf != 'ilp' and self.numCellsToNeighbors.get(self.preferredParent, 0) != 0)):
            # for the ILP SF, you can have no cell to your parent and still enqueue. It will be dropped.
            self._stats_incrementMoteStats('rplTxDAO')

            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.initiatedDAO += 1
            elif not self.settings.convergeFirst:
                self.initiatedDAO += 1

            # create new packet
            newPacket = {
                'asn': self.engine.getAsn(),
                'type': RPL_TYPE_DAO,
                'code': None,
                'payload': [self.id, self.preferredParent.id],
                'retriesLeft': TSCH_MAXTXRETRIES,
                'srcIp': self,
                'dstIp': self.dagRootAddress,
                'sourceRoute': []
            }

            # enqueue packet in TSCH queue
            if not self._tsch_enqueue(newPacket):
                # update mote stats
                self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

    def _rpl_schedule_sendDIO(self, firstDIO=False):

        if (not hasattr(self.settings, 'dioPeriod')) or self.settings.dioPeriod == 0:
            # disable DIO
            return

        with self.dataLock:

            asn = self.engine.getAsn()

            if self.settings.bayesianBroadcast:
                futureAsn = int(self.settings.slotframeLength)
            else:
                futureAsn = int(math.ceil(
                    self.genEBDIO.uniform(0.8 * self.settings.dioPeriod,
                                   1.2 * self.settings.dioPeriod) / self.settings.slotDuration))

            # schedule at start of next cycle
            self.engine.scheduleAtAsn(
                asn=asn + futureAsn,
                cb=self._rpl_action_sendDIO,
                uniqueTag=(self.id, '_rpl_action_sendDIO'),
                priority=3,
            )

    def _rpl_schedule_sendDAO(self, firstDAO=False):

        if (not hasattr(self.settings, 'daoPeriod')) or self.settings.daoPeriod == 0:
            # disable DAO
            return

        with self.dataLock:

            asn = self.engine.getAsn()

            if not firstDAO:
                futureAsn = int(math.ceil(
                    self.genEBDIO.uniform(0.8 * self.settings.daoPeriod, 1.2 * self.settings.daoPeriod) / (
                        self.settings.slotDuration)))
            else:
                futureAsn = 1

            # schedule at start of next cycle
            self.engine.scheduleAtAsn(
                asn=asn + futureAsn,
                cb=self._rpl_action_sendDAO,
                uniqueTag=(self.id, '_rpl_action_sendDAO'),
                priority=3,
            )

    def _rpl_action_receiveDIO(self, type, smac, payload):

        with self.dataLock:

            if self.dagRoot:
                return

            if not self.isSync:
                return

            self._log(INFO, "[rpl] Received DIO from mote {0}", (smac.id,))

            # update my mote stats
            self._stats_incrementMoteStats('rplRxDIO')

            sender = smac

            rank = payload[0]

            # don't update poor link
            if self._rpl_calcRankIncrease(sender) > RPL_MAX_RANK_INCREASE:
                return

            # update rank/DAGrank with sender
            self.neighborDagRank[sender] = rank / RPL_MIN_HOP_RANK_INCREASE
            self.neighborRank[sender] = rank

            # update number of DIOs received from sender
            if sender not in self.rplRxDIO:
                self.rplRxDIO[sender] = 0
            self.rplRxDIO[sender] += 1

            # housekeeping
            self._rpl_housekeeping()

            # update time correction
            if self.preferredParent == sender:
                asn = self.engine.getAsn()
                self.timeCorrectedSlot = asn

    def _rpl_action_receiveDAO(self, type, smac, payload):

        with self.dataLock:
            assert self.dagRoot

            self._stats_incrementMoteStats('rplRxDAO')

            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.receivedDAO += 1
            elif not self.settings.convergeFirst:
                self.receivedDAO += 1

            self.parents.update({tuple([payload[0]]): [[payload[1]]]})

            self._log(
                INFO,
                "Received a DAO!"
            )

    def _rpl_action_sendDIO(self):

        with self.dataLock:

            # assert False

            if self.settings.bayesianBroadcast:
                dioProb = float(self.settings.dioProbability) / float(len(self.join_joinedNeighbors())) if len(
                    self.join_joinedNeighbors()) else float(self.settings.dioProbability)
                sendDio = True if self.genEBDIO.random() < dioProb else False
            else:
                sendDio = True

            if sendDio:
                self._rpl_action_enqueueDIO()

            self._rpl_schedule_sendDIO()  # schedule next DIO

    def _rpl_action_sendDAO(self):

        with self.dataLock:

            self._rpl_action_enqueueDAO()
            self._rpl_schedule_sendDAO()  # schedule next DAO

    def _rpl_housekeeping(self):

        with self.dataLock:

            # ===
            # refresh the following parameters:
            # - self.preferredParent
            # - self.rank
            # - self.dagRank
            # - self.parentSet

            # calculate my potential rank with each of the motes I have heard a DIO from
            potentialRanks = {}
            for (neighbor, neighborRank) in self.neighborRank.items():
                # calculate the rank increase to that neighbor
                rankIncrease = self._rpl_calcRankIncrease(neighbor)
                if (((self.settings.changeParent == 1 and (self.preferredParent == None or (self.engine.asn > self.engine.asnInitExperiment and self.preferredParent != None))) or \
                      (self.preferredParent == None and self.settings.changeParent == 0)) and \
                     rankIncrease != None and rankIncrease <= min([RPL_MAX_RANK_INCREASE, RPL_MAX_TOTAL_RANK - neighborRank])):
                    # check if there is a loop and if exists, skip the neighbor
                    rootReached = False
                    skipNeighbor = False
                    inode = neighbor
                    while rootReached == False:
                        if inode.preferredParent != None:
                            if inode.preferredParent.id == self.id:
                                skipNeighbor = True
                            if inode.preferredParent.id == 0:
                                rootReached = True
                            else:
                                inode = inode.preferredParent
                        else:
                            rootReached = True
                    if skipNeighbor == True:
                        continue
                    potentialRanks[neighbor] = neighborRank + rankIncrease

            # sort potential ranks
            sorted_potentialRanks = sorted(potentialRanks.iteritems(), key=lambda x: x[1])

            # switch parents only when rank difference is large enough
            for i in range(1, len(sorted_potentialRanks)):
                if sorted_potentialRanks[i][0] in self.parentSet:
                    # compare the selected current parent with motes who have lower potential ranks
                    # and who are not in the current parent set
                    for j in range(i):
                        if sorted_potentialRanks[j][0] not in self.parentSet:
                            if sorted_potentialRanks[i][1] - sorted_potentialRanks[j][1] < RPL_PARENT_SWITCH_THRESHOLD:
                                mote_rank = sorted_potentialRanks.pop(i)
                                sorted_potentialRanks.insert(j, mote_rank)
                                break

            # pick my preferred parent and resulting rank
            if sorted_potentialRanks:
                oldParentSet = set([parent.id for parent in self.parentSet])

                (newPreferredParent, newrank) = sorted_potentialRanks[0]

                # compare a current preferred parent with new one
                if self.preferredParent and newPreferredParent != self.preferredParent:
                    for (mote, rank) in sorted_potentialRanks[:RPL_PARENT_SET_SIZE]:

                        if mote == self.preferredParent:
                            # switch preferred parent only when rank difference is large enough
                            if rank - newrank < RPL_PARENT_SWITCH_THRESHOLD:
                                (newPreferredParent, newrank) = (mote, rank)

                # update mote stats
                if self.rank and newrank != self.rank:
                    self._stats_incrementMoteStats('rplChurnRank')
                    # log
                    self._log(
                        INFO,
                        "[rpl] churn: rank {0}->{1}",
                        (self.rank, newrank),
                    )
                if self.preferredParent is None and newPreferredParent is not None:
                    if not self.settings.withJoin:
                        # if we selected a parent for the first time, add one cell to it
                        # upon successful join, the reservation request is scheduled explicitly
                        if _msf_is_enabled():
                            self._msf_schedule_parent_change()
                elif self.preferredParent != newPreferredParent:
                    # update mote stats
                    self._stats_incrementMoteStats('rplChurnPrefParent')
                    self.rplPrefParentChurns += 1
                    self.rplPrefParentChurnToAndASN = (newPreferredParent, self.engine.asn)

                    # log
                    self._log(
                        INFO,
                        "[rpl] churn: preferredParent {0}->{1}",
                        (self.preferredParent.id, newPreferredParent.id),
                    )
                    # trigger 6P add to the new parent
                    self.oldPreferredParent = self.preferredParent
                    if _msf_is_enabled():
                        self._msf_schedule_parent_change()

                if self.preferredParent is not None and self.id in self.preferredParent.childrenRPL:
                    self.preferredParent.childrenRPL.remove(self.id)

                # store new preferred parent and rank
                (self.preferredParent, self.rank) = (newPreferredParent, newrank)

                if self.id not in self.preferredParent.childrenRPL:
                    self.preferredParent.childrenRPL.append(self.id)
                else:
                    assert False # should not be in here.

                # calculate DAGrank
                self.dagRank = int(self.rank / RPL_MIN_HOP_RANK_INCREASE)

                # pick my parent set
                self.parentSet = [n for (n, _) in sorted_potentialRanks if self.neighborRank[n] < self.rank][
                                 :RPL_PARENT_SET_SIZE]
                assert self.preferredParent in self.parentSet

                if oldParentSet != set([parent.id for parent in self.parentSet]):
                    self._stats_incrementMoteStats('rplChurnParentSet')

    def _rpl_calcRankIncrease(self, neighbor):

        with self.dataLock:
            # estimate the ETX to that neighbor
            etx = self._estimateETX(neighbor)

            # return if that failed
            if not etx:
                return

            # per draft-ietf-6tisch-minimal, rank increase is (3*ETX-2)*RPL_MIN_HOP_RANK_INCREASE
            return int(((3 * etx) - 2) * RPL_MIN_HOP_RANK_INCREASE)

    def _rpl_getSourceRoute(self, destAddr):
        """
        Retrieve the source route to a given mote.

        :param destAddr: [in] The EUI64 address of the final destination.

        :returns: The source route, a list of EUI64 address, ordered from
            destination to source.
        """

        sourceRoute = []
        with self.dataLock:
            parents = self.parents
            self._rpl_getSourceRoute_internal(destAddr, sourceRoute, parents)

        if sourceRoute:
            sourceRoute.pop()

        return sourceRoute

    def _rpl_getSourceRoute_internal(self, destAddr, sourceRoute, parents):

        if not destAddr:
            # no more parents
            return

        if not parents.get(tuple(destAddr)):
            # this node does not have a list of parents
            return

        # first time add destination address
        if destAddr not in sourceRoute:
            sourceRoute += [destAddr]

        # pick a parent
        parent = parents.get(tuple(destAddr))[0]

        # avoid loops
        if parent not in sourceRoute:
            sourceRoute += [parent]

            # add non empty parents recursively
            nextparent = self._rpl_getSourceRoute_internal(parent, sourceRoute, parents)

            if nextparent:
                sourceRoute += [nextparent]

    def _rpl_addNextHop(self, packet):
        assert self != packet['dstIp']

        if not (self.preferredParent or self.dagRoot):
            return False

        nextHop = None

        if packet['dstIp'] == BROADCAST_ADDRESS:
            nextHop = self._myNeighbors() # mobility: OK.
        # 6Top packet. don't send to the parent necessarily. Send it directly to your neighbor (1 hop)
        elif packet['type'] == IANA_6TOP_TYPE_REQUEST or packet['type'] == IANA_6TOP_TYPE_RESPONSE:
            nextHop = [packet['dstIp']]
        elif packet['dstIp'] == self.dagRootAddress:  # upward packet
            nextHop = [self.preferredParent]
        elif packet['sourceRoute']:  # downward packet with source route info filled correctly
            nextHopId = packet['sourceRoute'].pop()
            for nei in self._myNeighbors(): # mobility: OK.
                if [nei.id] == nextHopId:
                    nextHop = [nei]
        elif packet['dstIp'] in self._myNeighbors():  # mobility: OK. Used for 1hop packets, such as 6top messages. This has to be the last one, since some neighbours can have very low PDR
            nextHop = [packet['dstIp']]

        packet['nextHop'] = nextHop
        return True if nextHop else False

    # ===== msf
    def _msf_is_enabled(self):
        if not hasattr(self.settings, 'disableMSF'):
            return True
        if self.settings.disableMSF is False:
            return True
        return False

    def _msf_schedule_parent_change(self):
        """
          Schedule MSF parent change
        """
        self.engine.scheduleAtAsn(
            asn=int(self.engine.asn + (1 + self.settings.slotframeLength * 16 * self.genMSF.random())),
            cb=self._msf_action_parent_change,
            uniqueTag=(self.id, '_msf_action_parent_change'),
            priority=4,
        )

    def _msf_action_parent_change(self):
        """
          Trigger MSF parent change: Add the same number of cells to the new parent as we had with the old one.
          In the case of bootstrap, add one cell to the preferred parent.
        """
        assert self.preferredParent

        with self.dataLock:

            armTimeout = False
            armTimeoutRemoval = False

            celloptions = DIR_TXRX_SHARED

            if self.numCellsToNeighbors.get(self.preferredParent, 0) == 0:
                timeout = self._msf_get_sixtop_timeout(self.preferredParent)

                self._log(INFO,
                          "[msf] triggering 6P ADD of {0} cells, dir {1}, to mote {2}, 6P timeout {3} (parent change)",
                          (self.settings.msfNumCellsToAddOrRemove, celloptions, self.preferredParent.id, timeout,))

                self._log(INFO,
                          "[msf] cells to old {0}, cells to new {1}",
                          (self.numCellsToNeighbors.get(self.oldPreferredParent, 0), self.numCellsToNeighbors.get(
                              self.preferredParent, 0)))

                self._sixtop_cell_reservation_request(self.preferredParent,
                                                      self.numCellsToNeighbors.get(self.oldPreferredParent, self.settings.minCellsMSF),
                                                      # request at least one cell
                                                      celloptions, timeout)

                self.currentOldPrefParentRemoval = 0

            elif self.currentOldPrefParentRemoval < MSF_MAX_OLD_PARENT_REMOVAL and \
                    self.numCellsToNeighbors.get(self.oldPreferredParent, 0) > 0 and \
                    self.numCellsToNeighbors.get(self.preferredParent, 0) > 0:
                timeout = self._msf_get_sixtop_timeout(self.oldPreferredParent)

                # initiate actual old parent change removal
                self.oldPrefParentRemoval += 1
                self.currentOldPrefParentRemoval += 1

                self._log(INFO,
                          "[msf] triggering 6P REMOVE of {0} cells, dir {1}, to mote {2}, 6P timeout {3} (parent change)",
                          (self.settings.msfNumCellsToAddOrRemove, celloptions, self.oldPreferredParent.id, timeout,))

                self._sixtop_removeCells(self.oldPreferredParent,
                                         self.numCellsToNeighbors.get(self.oldPreferredParent, 0), celloptions, timeout)

            # if this is the first parent and looking for convergence
            if self.oldPreferredParent is None:
                # always schedule a new one
                self.engine.scheduleIn(
                    delay=25,
                    cb=self._msf_action_parent_change,
                    uniqueTag=(self.id, '_msf_action_parent_change'),
                    priority=4,
                )
            else:
                # always schedule a new one
                self.engine.scheduleIn(
                    delay=300,
                    cb=self._msf_action_parent_change,
                    uniqueTag=(self.id, '_msf_action_parent_change'),
                    priority=4,
                )

            if (self.numCellsToNeighbors.get(self.preferredParent, 0) > 0 and \
                self.numCellsToNeighbors.get(self.oldPreferredParent, 0) == 0) or \
                self.currentOldPrefParentRemoval == MSF_MAX_OLD_PARENT_REMOVAL:

                assert self.numCellsToNeighbors.get(self.preferredParent, 0) or self.currentOldPrefParentRemoval == MSF_MAX_OLD_PARENT_REMOVAL
                assert self.numCellsToNeighbors.get(self.oldPreferredParent, 0) == 0 or self.currentOldPrefParentRemoval == MSF_MAX_OLD_PARENT_REMOVAL
                # upon success, invalidate old parent

                self.currentOldPrefParentRemoval = 0

                # remove it
                self._log(
                    INFO,
                    '[6top] Retransmission parent change event is being removed...',
                )
                self.engine.removeEvent((self.id,
                                         '_msf_action_parent_change'))  # remove the pending retransmission event for MSF

                self.oldPreferredParent = None

    def _msf_get_sixtop_timeout(self, neighbor):
        """
          calculate the timeout to a neighbor according to MSF
        """
        cellPDR = []
        for (ts, cell) in self.schedule.iteritems():
            if (cell['neighbor'] == neighbor and cell['dir'] == DIR_TX) or (cell['dir'] == DIR_TXRX_SHARED and cell['neighbor'] == neighbor):
                cellPDR.append(self.getCellPDR(cell))

        self._log(INFO, '[sixtop] timeout() cellPDR = {0}', (cellPDR,))

        if len(cellPDR) > 0:
            meanPDR = sum(cellPDR) / float(len(cellPDR))
            if meanPDR < 0.00001:
                return MSF_DEFAULT_SIXTOP_TIMEOUT
            assert meanPDR <= 1.0
            timeout = math.ceil(
                (float(self.settings.slotframeLength * self.settings.slotDuration) / float(len(cellPDR))) * (
                    float(1 / meanPDR)) * MSF_6PTIMEOUT_SEC_FACTOR)
            return timeout
        else:
            return MSF_DEFAULT_SIXTOP_TIMEOUT

    def _msf_signal_cell_used(self, neighbor, cellOptions, direction=None, type=None):
        assert cellOptions in [DIR_TXRX_SHARED, DIR_TX, DIR_RX]
        assert direction in [DIR_TX, DIR_RX]
        assert type is not None

        with self.dataLock:
            # MSF: updating numCellsUsed
            if cellOptions == DIR_TXRX_SHARED and neighbor == self.preferredParent:
                self._log(INFO,
                          '[msf] _msf_signal_cell_used: neighbor {0} direction {1} type {2} preferredParent = {3}',
                          (neighbor.id, direction, type, self.preferredParent.id))
                self.numCellsUsed += 1

    def _msf_signal_cell_elapsed(self, neighbor, direction):

        assert self.numCellsElapsed <= self.settings.msfMaxNumCells
        assert direction in [DIR_TXRX_SHARED, DIR_TX, DIR_RX]

        with self.dataLock:
            # MSF: updating numCellsElapsed
            if direction == DIR_TXRX_SHARED and neighbor == self.preferredParent:
                self.numCellsElapsed += 1

                if self.numCellsElapsed == self.settings.msfMaxNumCells:
                    self._log(INFO, '[msf] _msf_signal_cell_elapsed: numCellsElapsed = {0}, numCellsUsed = {1}',
                              (self.numCellsElapsed, self.numCellsUsed))

                    # if self.numCellsUsed > self.settings.msfLimNumCellsUsedHigh:
                    #     self._msf_schedule_bandwidth_increment()
                    # elif self.numCellsUsed < self.settings.msfLimNumCellsUsedLow:
                    #     self._msf_schedule_bandwidth_decrement()
                    self._msf_reset_counters()

    def _msf_reset_counters(self):
        with self.dataLock:
            self.numCellsElapsed = 0
            self.numCellsUsed = 0

    def _msf_schedule_bandwidth_increment(self):
        """
          Schedule MSF bandwidth increment
        """
        self.engine.scheduleAtAsn(
            asn=int(self.engine.asn + 1),
            cb=self._msf_action_bandwidth_increment,
            uniqueTag=(self.id, '_msf_action_bandwidth_increment'),
            priority=4,
        )

    def _msf_action_bandwidth_increment(self):
        """
          Trigger 6P to add msfNumCellsToAddOrRemove cells to preferred parent
        """
        timeout = self._msf_get_sixtop_timeout(self.preferredParent)
        celloptions = DIR_TXRX_SHARED
        self._log(INFO,
                  "[msf] triggering 6P ADD of {0} cells, dir {1}, to mote {2}, 6P timeout {3}",
                  (self.settings.msfNumCellsToAddOrRemove, DIR_TXRX_SHARED, self.preferredParent.id, timeout,))
        self._sixtop_cell_reservation_request(self.preferredParent,
                                              self.settings.msfNumCellsToAddOrRemove,
                                              celloptions, timeout)

    def _msf_schedule_bandwidth_decrement(self):
        """
          Schedule MSF bandwidth decrement
        """
        self.engine.scheduleAtAsn(
            asn=int(self.engine.asn + 1),
            cb=self._msf_action_bandwidth_decrement,
            uniqueTag=(self.id, '_msf_action_bandwidth_decrement'),
            priority=4,
        )

    def _msf_action_bandwidth_decrement(self):
        """
          Trigger 6P to remove msfNumCellsToAddOrRemove cells from preferred parent
        """
        # ensure at least one dedicated cell is kept with preferred parent
        if self.numCellsToNeighbors.get(self.preferredParent, 0) > self.settings.minCellsMSF:
            timeout = self._msf_get_sixtop_timeout(self.preferredParent)
            celloptions = DIR_TXRX_SHARED
            self._log(INFO,
                      "[msf] triggering 6P REMOVE of {0} cells, dir {1}, to mote {2}, 6P timeout {3}",
                      (self.settings.msfNumCellsToAddOrRemove, DIR_TXRX_SHARED, self.preferredParent.id, timeout,))

            # trigger 6p to remove msfNumCellsToAddOrRemove cells
            self._sixtop_removeCells(self.preferredParent, self.settings.msfNumCellsToAddOrRemove, celloptions, timeout)

    def _msf_schedule_housekeeping(self):

        self.engine.scheduleIn(
            delay=self.settings.msfHousekeepingPeriod * (0.9 + 0.2 * self.genMSF.random()),
            cb=self._msf_action_housekeeping,
            uniqueTag=(self.id, '_msf_action_housekeeping'),
            priority=4,
        )

    def _msf_action_housekeeping(self):
        """
        MSF housekeeping: decides when to relocate cells
        """

        with self.dataLock:
            if self.dagRoot:
                return

            # TODO MSF relocation algorithm

            # schedule next housekeeping
            self._msf_schedule_housekeeping()

    # ===== 6top

    def _sixtop_timer_fired(self):
        found = False
        for n in self.sixtopStates.keys():
            if 'tx' in self.sixtopStates[n] and 'timer' in self.sixtopStates[n]['tx'] and \
                    self.sixtopStates[n]['tx']['timer']['asn'] == self.engine.getAsn():  # if it is this ASN, we have the correct state and we have to abort it
                self.sixtopStates[n]['tx']['state'] = SIX_STATE_IDLE  # put back to IDLE
                self.sixtopStates[n]['tx']['blockedCells'] = []  # transaction gets aborted, so also delete the blocked cells
                del self.sixtopStates[n]['tx']['timer']
                found = True
                # log
                self._log(
                    INFO,
                    "[6top] fired timer on mote {0} for neighbor {1}.",
                    (self.id, n),
                )

        if not found:  # if we did not find it, assert
            assert False

    def _sixtop_cell_reservation_request(self, neighbor, numCells, dir, timeout):
        """ tries to reserve numCells cells to a neighbor. """

        with self.dataLock:
            if self.settings.sixtopMessaging:
                if neighbor.id not in self.sixtopStates or \
                        (neighbor.id in self.sixtopStates and 'tx' not in self.sixtopStates[neighbor.id] and self.sixtopStates[neighbor.id]['rx']['state'] == SIX_STATE_IDLE) or \
                        (neighbor.id in self.sixtopStates and 'tx' in self.sixtopStates[neighbor.id] and self.sixtopStates[neighbor.id]['tx']['state'] == SIX_STATE_IDLE):

                    self._log(
                        INFO,
                        "[6P] sixtop cell reservation.",
                    )

                    # if neighbor not yet in states dict, add it
                    if neighbor.id not in self.sixtopStates:
                        self.sixtopStates[neighbor.id] = {}
                    if 'tx' not in self.sixtopStates[neighbor.id]:
                        self.sixtopStates[neighbor.id]['tx'] = {}
                        self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []
                        self.sixtopStates[neighbor.id]['tx']['seqNum'] = 0
                    self.sixtopStates[neighbor.id]['tx']['timeout'] = timeout

                    if self.eLLSF is None:  # do normal 6top reservation
                        # get blocked cells from other 6top operations
                        blockedCells = []
                        for n in self.sixtopStates.keys():
                            if n != neighbor.id:
                                if 'tx' in self.sixtopStates[n] and len(self.sixtopStates[n]['tx']['blockedCells']) > 0:
                                    blockedCells += self.sixtopStates[n]['tx']['blockedCells']
                                if 'rx' in self.sixtopStates[n] and len(self.sixtopStates[n]['rx']['blockedCells']) > 0:
                                    blockedCells += self.sixtopStates[n]['rx']['blockedCells']

                        # convert blocked cells into ts
                        tsBlocked = []
                        if len(blockedCells) > 0:
                            for c in blockedCells:
                                tsBlocked.append(c[0])

                        # randomly picking cells
                        availableTimeslots = list(
                            set(range(self.settings.slotframeLength)) - set(self.schedule.keys()) - set(tsBlocked))
                        self.genMSF.shuffle(availableTimeslots)
                        
                        cellList = []
                        if self.settings.individualModulations == 1:
                            # cellList = []
                            indexInAvailableSlots = 0
                            while len(cellList) < (numCells * MSF_MIN_NUM_CELLS) and indexInAvailableSlots < len(availableTimeslots):
                                s = availableTimeslots[indexInAvailableSlots]
                                allFree = True
                                necessarySlots = []
                                for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                                    necessarySlots += [s + i]
                                for nSlot in necessarySlots:
                                    if nSlot not in availableTimeslots:
                                        allFree = False
                                if allFree:
                                    cellList += [(necessarySlots[0], self.genMSF.randint(0, self.settings.numChans - 1), dir)]
                                indexInAvailableSlots += 1
                        else:
                            cells = dict([(ts, self.genMSF.randint(0, self.settings.numChans - 1)) for ts in
                                          availableTimeslots[:numCells * MSF_MIN_NUM_CELLS]])
                            cellList = [(ts, ch, dir) for (ts, ch) in cells.iteritems()]

                        self._sixtop_enqueue_ADD_REQUEST(neighbor, cellList, numCells, dir,
                                                         self.sixtopStates[neighbor.id]['tx']['seqNum'])
                    elif self.eLLSF is not None:
                        self._log(
                            DEBUG,
                            "[6top] numCells {0}, MSF_MIN_NUM_CELLS {1}.",
                            (numCells, MSF_MIN_NUM_CELLS),
                        )
                        cellList = self.eLLSF._ellsf_reservation_request(neighbor, numCells * MSF_MIN_NUM_CELLS, dir)
                        self._log(
                            DEBUG,
                            "[6top] {0}.",
                            (cellList,),
                        )
                        if cellList != []:  # only send the request if we found (an) appropriate cell(s)
                            self._sixtop_enqueue_ADD_REQUEST(neighbor, cellList, numCells, dir,
                                                             self.sixtopStates[neighbor.id]['tx']['seqNum'])
                else:
                    self._log(
                        DEBUG,
                        "[6top] can not send 6top ADD request to {0} because timer still did not fire on mote {1} to mote {2}: {3}",
                        (neighbor.id, self.id, neighbor.id, self.sixtopStates[neighbor.id]['tx']['timeout']),
                    )

            else:
                cells = neighbor._sixtop_cell_reservation_response(self, numCells, dir)

                cellList = []
                for (ts, ch) in cells.iteritems():
                    # log
                    self._log(
                        INFO,
                        '[6top] add TX cell ts={0},ch={1} from {2} to {3}',
                        (ts, ch, self.id, neighbor.id),
                    )
                    cellList += [(ts, ch, dir)]
                self._tsch_addCells(neighbor, cellList)

                # update counters
                if dir == DIR_TX:
                    if neighbor not in self.numCellsToNeighbors:
                        self.numCellsToNeighbors[neighbor] = 0
                    self.numCellsToNeighbors[neighbor] += len(cells)
                elif dir == DIR_RX:
                    if neighbor not in self.numCellsFromNeighbors:
                        self.numCellsFromNeighbors[neighbor] = 0
                    self.numCellsFromNeighbors[neighbor] += len(cells)
                else:
                    if neighbor not in self.numCellsFromNeighbors:
                        self.numCellsFromNeighbors[neighbor] = 0
                    self.numCellsFromNeighbors[neighbor] += len(cells)
                    if neighbor not in self.numCellsToNeighbors:
                        self.numCellsToNeighbors[neighbor] = 0
                    self.numCellsToNeighbors[neighbor] += len(cells)

                if len(cells) != numCells:
                    # log
                    self._log(
                        ERROR,
                        '[6top] scheduled {0} cells out of {1} required between motes {2} and {3}. cells={4}',
                        (len(cells), numCells, self.id, neighbor.id, cells),
                    )

    def _sixtop_enqueue_ADD_REQUEST(self, neighbor, cellList, numCells, dir, seq):
        """ enqueue a new 6P ADD request """

        self._log(
            INFO,
            '[6top] enqueueing a new 6P ADD message (seqNum = {0}) cellList={1}, numCells={2} from {3} to {4}',
            (seq, cellList, numCells, self.id, neighbor.id),
        )

        # create new packet
        newPacket = {
            'asn': self.engine.getAsn(),
            'type': IANA_6TOP_TYPE_REQUEST,
            'code': IANA_6TOP_CMD_ADD,
            'payload': [cellList, numCells, dir, seq, self.engine.getAsn()],
            'retriesLeft': TSCH_MAXTXRETRIES,
            'srcIp': self,
            'dstIp': neighbor,  # currently upstream
            'sourceRoute': [],
        }

        # enqueue packet in TSCH queue
        isEnqueued = self._tsch_enqueue(newPacket)

        if not isEnqueued:
            self._log(
                INFO,
                '[6top] ADD Request did not get enqueued.'
            )
            # update mote stats
            self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

        else:
            self._log(
                INFO,
                '[6top] ADD Request got enqueued.'
            )

            if self.settings.individualModulations == 1:
                blockedCellList = []
                addedBlocked = []
                for idx, c in enumerate(cellList):
                    for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                        tmpCell = [(cellList[idx][0] + i, cellList[idx][1], cellList[idx][2])]
                        tmpTs = cellList[idx][0] + i
                        if tmpTs not in addedBlocked:
                            blockedCellList += tmpCell
                            addedBlocked += [tmpTs]
                # set state to sending request for this neighbor
                self.sixtopStates[neighbor.id]['tx']['blockedCells'] = blockedCellList
            else:
                self.sixtopStates[neighbor.id]['tx']['blockedCells'] = cellList

            # set state to sending request for this neighbor
            self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_SENDING_REQUEST

    def _sixtop_receive_ADD_REQUEST(self, type, smac, payload):
        with self.dataLock:
            neighbor = smac
            cellList = payload[0]
            numCells = payload[1]
            dirNeighbor = payload[2]
            seq = payload[3]

            # has the asn of when the req packet was enqueued in the neighbor
            self.tsSixTopReqRecv[neighbor] = payload[4]
            self._stats_incrementMoteStats('6topRxAddReq')

            if smac.id in self.sixtopStates and 'rx' in self.sixtopStates[smac.id] and self.sixtopStates[smac.id]['rx'][
                'state'] != SIX_STATE_IDLE:
                for pkt in self.txQueue:
                    if pkt['type'] == IANA_6TOP_TYPE_RESPONSE and pkt['dstIp'].id == smac.id:
                        self.txQueue.remove(pkt)
                        self._log(
                            INFO,
                            "[6top] removed a 6TOP_TYPE_RESPONSE packet (seqNum = {0}) in the queue of mote {1} to neighbor {2}, because a new TYPE_REQUEST (add, seqNum = {3}) was received.",
                            (pkt['payload'][3], self.id, smac.id, seq),
                        )
                        # assert False
                returnCode = IANA_6TOP_RC_RESET  # error, neighbor has to abort transaction
                if smac.id not in self.sixtopStates:
                    self.sixtopStates[smac.id] = {}
                if 'rx' not in self.sixtopStates[smac.id]:
                    self.sixtopStates[smac.id]['rx'] = {}
                    self.sixtopStates[smac.id]['rx']['blockedCells'] = []
                    self.sixtopStates[smac.id]['rx']['seqNum'] = 0
                self.sixtopStates[smac.id]['rx']['state'] = SIX_STATE_REQUEST_ADD_RECEIVED
                self._sixtop_enqueue_RESPONSE(neighbor, [], returnCode, dirNeighbor, seq)

                return

            # go to the correct state
            # set state to receiving request for this neighbor
            if smac.id not in self.sixtopStates:
                self.sixtopStates[smac.id] = {}
            if 'rx' not in self.sixtopStates[smac.id]:
                self.sixtopStates[smac.id]['rx'] = {}
                self.sixtopStates[smac.id]['rx']['blockedCells'] = []
                self.sixtopStates[smac.id]['rx']['seqNum'] = 0

            self.sixtopStates[smac.id]['rx']['state'] = SIX_STATE_REQUEST_ADD_RECEIVED

            # set direction of cells
            if dirNeighbor == DIR_TX:
                newDir = DIR_RX
            elif dirNeighbor == DIR_RX:
                newDir = DIR_TX
            else:
                newDir = DIR_TXRX_SHARED

            # cells that will be in the response
            newCellList = []

            if self.eLLSF is None:
                # get blocked cells from other 6top operations
                blockedCells = []
                for n in self.sixtopStates.keys():
                    if n != neighbor.id:
                        if 'rx' in self.sixtopStates[n] and len(self.sixtopStates[n]['rx']['blockedCells']) > 0:
                            blockedCells += self.sixtopStates[n]['rx']['blockedCells']
                        if 'tx' in self.sixtopStates[n] and len(self.sixtopStates[n]['tx']['blockedCells']) > 0:
                            blockedCells += self.sixtopStates[n]['tx']['blockedCells']
                # convert blocked cells into ts
                tsBlocked = []
                if len(blockedCells) > 0:
                    for c in blockedCells:
                        tsBlocked.append(c[0])

                # available timeslots on this mote
                availableTimeslots = list(
                    set(range(self.settings.slotframeLength)) - set(self.schedule.keys()) - set(tsBlocked))

                self.genMSF.shuffle(cellList)
                if self.settings.individualModulations == 1:
                    for (ts, ch, dir) in cellList:
                        if len(newCellList) == numCells:
                            break
                        s = ts
                        allFree = True
                        for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                            tmpTs = s + i
                            if tmpTs not in availableTimeslots:
                                allFree = False
                        if allFree:
                            newCellList += [(ts, ch, newDir)]
                else:
                    for (ts, ch, dir) in cellList:
                        if len(newCellList) == numCells:
                            break
                        if ts in availableTimeslots:
                            newCellList += [(ts, ch, newDir)]

                #  if len(newCellList) < numCells it is considered still a success as long as len(newCellList) is bigger than 0
                if len(newCellList) <= 0:
                    returnCode = IANA_6TOP_RC_NORES  # not enough resources
                else:
                    returnCode = IANA_6TOP_RC_SUCCESS  # enough resources


                if self.settings.individualModulations == 1:
                    blockedCellList = []
                    addedBlocked = []
                    for idx, c in enumerate(newCellList):
                        for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                            tmpCell = [(newCellList[idx][0] + i, newCellList[idx][1], newCellList[idx][2])]
                            tmpTs = newCellList[idx][0] + i
                            if tmpTs not in addedBlocked:
                                blockedCellList += tmpCell
                                addedBlocked += [tmpTs]
                            else:
                                assert False
                    # set blockCells for this 6top operation
                    self.sixtopStates[neighbor.id]['rx']['blockedCells'] = blockedCellList
                else:
                    # set blockCells for this 6top operation
                    self.sixtopStates[neighbor.id]['rx']['blockedCells'] = newCellList

                # enqueue response
                self._sixtop_enqueue_RESPONSE(neighbor, newCellList, returnCode, newDir, seq)
            elif self.eLLSF is not None:
                newCellList, returnCode = self.eLLSF._ellsf_receive_request(neighbor, numCells, newDir, cellList)
                # enqueue response
                self._sixtop_enqueue_RESPONSE(neighbor, newCellList, returnCode, newDir, seq)

    def _sixtop_cell_reservation_response(self, neighbor, numCells, dirNeighbor):
        """ get a response from the neighbor. """

        with self.dataLock:

            # set direction of cells
            if dirNeighbor == DIR_TX:
                newDir = DIR_RX
            elif dirNeighbor == DIR_RX:
                newDir = DIR_TX
            else:
                newDir = DIR_TXRX_SHARED

            availableTimeslots = list(
                set(range(self.settings.slotframeLength)) - set(neighbor.schedule.keys()) - set(self.schedule.keys()))
            self.genMSF.shuffle(availableTimeslots)
            cells = dict([(ts, self.genMSF.randint(0, self.settings.numChans - 1)) for ts in availableTimeslots[:numCells]])
            cellList = []

            for ts, ch in cells.iteritems():
                # log
                self._log(
                    INFO,
                    '[6top] add RX cell ts={0},ch={1} from {2} to {3}',
                    (ts, ch, self.id, neighbor.id),
                )
                cellList += [(ts, ch, newDir)]
            self._tsch_addCells(neighbor, cellList)

            # update counters
            if newDir == DIR_TX:
                if neighbor not in self.numCellsToNeighbors:
                    self.numCellsToNeighbors[neighbor] = 0
                self.numCellsToNeighbors[neighbor] += len(cells)
            elif newDir == DIR_RX:
                if neighbor not in self.numCellsFromNeighbors:
                    self.numCellsFromNeighbors[neighbor] = 0
                self.numCellsFromNeighbors[neighbor] += len(cells)
            else:
                if neighbor not in self.numCellsFromNeighbors:
                    self.numCellsFromNeighbors[neighbor] = 0
                self.numCellsFromNeighbors[neighbor] += len(cells)
                if neighbor not in self.numCellsToNeighbors:
                    self.numCellsToNeighbors[neighbor] = 0
                self.numCellsToNeighbors[neighbor] += len(cells)

            return cells

    def _sixtop_enqueue_RESPONSE(self, neighbor, cellList, returnCode, dir, seq):
        """ enqueue a new 6P ADD or DELETE response """

        self._log(
            INFO,
            '[6top] enqueueing a new 6P RESPONSE message cellList={0}, numCells={1}, returnCode={2}, seqNum={3} from {4} to {5} (txQueue len: {6})',
            (cellList, len(cellList), returnCode, seq, self.id, neighbor.id, len(self.txQueue)),
        )

        # create new packet
        newPacket = {
            'asn': self.engine.getAsn(),
            'type': IANA_6TOP_TYPE_RESPONSE,
            'code': returnCode,
            'payload': [cellList, len(cellList), dir, seq],
            'retriesLeft': TSCH_MAXTXRETRIES,
            'srcIp': self,
            'dstIp': neighbor,  # currently upstream
            'sourceRoute': [],
        }

        # enqueue packet in TSCH queue
        isEnqueued = self._tsch_enqueue(newPacket)
        if not isEnqueued:
            # update mote stats
            self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

    def _sixtop_receive_RESPONSE(self, type, code, smac, payload):
        """ receive a 6P response messages """

        with self.dataLock:
            if self.sixtopStates[smac.id]['tx']['state'] == SIX_STATE_WAIT_ADDRESPONSE:
                # TODO: now this is still an assert, later this should be handled appropriately
                assert code == IANA_6TOP_RC_SUCCESS or code == IANA_6TOP_RC_NORES or code == IANA_6TOP_RC_RESET  # RC_BUSY not implemented yet

                self._stats_incrementMoteStats('6topRxAddResp')

                neighbor = smac
                receivedCellList = payload[0]
                numCells = payload[1]
                receivedDir = payload[2]
                seq = payload[3]

                # seqNum mismatch, transaction failed, ignore packet
                if seq != self.sixtopStates[neighbor.id]['tx']['seqNum']:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {1} has received a wrong seqNum in a sixtop operation with mote {0}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return False

                # transaction is considered as failed since the timeout has already scheduled for this ASN. Too late for removing the event, ignore packet
                if self.sixtopStates[neighbor.id]['tx']['timer']['asn'] == self.engine.getAsn():
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {1} has received a ADD response from mote {0} too late',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return False

                # delete the timer.
                uniqueTag = '_sixtop_timer_fired_dest_%s' % neighbor.id
                uniqueTag = (self.id, uniqueTag)
                self.engine.removeEvent(uniqueTag=uniqueTag)

                self._log(
                    INFO,
                    "[6top] removed timer for mote {0} to neighbor {1} on asn {2}, tag {3}",
                    (self.id, neighbor.id, self.sixtopStates[neighbor.id]['tx']['timer']['asn'], str(uniqueTag)),
                )
                del self.sixtopStates[neighbor.id]['tx']['timer']

                self.sixtopStates[smac.id]['tx']['seqNum'] += 1

                # if the request was successfull and there were enough resources
                if code == IANA_6TOP_RC_SUCCESS:
                    cellList = []

                    # set direction of cells
                    if receivedDir == DIR_TX:
                        newDir = DIR_RX
                    elif receivedDir == DIR_RX:
                        newDir = DIR_TX
                    else:
                        newDir = DIR_TXRX_SHARED

                    # add the time difference between the rpl pref parent churn and the actual adding of the cell
                    if neighbor == self.preferredParent and \
                        neighbor != self.oldPreferredParent and \
                        self.numCellsToNeighbors.get(self.preferredParent, 0) == 0:
                        if self.rplPrefParentChurnToAndASN[0] != None and neighbor != self.rplPrefParentChurnToAndASN[0]:
                            assert False
                        elif self.rplPrefParentChurnToAndASN[0] != None:
                            self.rplPrefParentASNDiffs.append(self.engine.asn - self.rplPrefParentChurnToAndASN[1])
                            self.rplPrefParentChurnToAndASN = (None, None) # reset it until the next RPL parent change

                    if self.settings.individualModulations == 1:
                        parentTs = None
                        first = True
                        for (ts, ch, cellDir) in receivedCellList:
                            if first:
                                parentTs = ts
                                first = False
                            # log
                            self._log(
                                INFO,
                                '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                (ts, ch, self.id, neighbor.id, newDir),
                            )
                            for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                                cellList += [(ts + i, ch, newDir)]
                                self._log(
                                    INFO,
                                    '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                    (ts + i, ch, self.id, neighbor.id, cellDir),
                                )
                        self._tsch_addCells(neighbor, cellList, parentTs=parentTs, modulation=self.modulation[neighbor])
                    else:
                        for (ts, ch, cellDir) in receivedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                (ts, ch, self.id, neighbor.id, newDir),
                            )
                            cellList += [(ts, ch, newDir)]
                        self._tsch_addCells(neighbor, cellList)

                    # test for convergence
                    if self.settings.convergeFirst and not self.isConverged and len(receivedCellList) > 0 \
                        and neighbor == self.preferredParent and (newDir == DIR_TX or newDir == DIR_TXRX_SHARED):
                        self.isConverged = True
                        self.isConvergedASN = self.engine.getAsn()
                        if all(mote.isConverged == True for mote in self.engine.motes):
                            self._log(
                                INFO,
                                'All motes converged: all have a cell to their parent.'
                            )
                            self.engine.dedicatedCellConvergence = self.engine.getAsn()
                            # experiment time in ASNs
                            simTime = self.settings.numCyclesPerRun * self.settings.slotframeLength
                            # offset until the end of the current cycle
                            offset = self.settings.slotframeLength - (self.engine.asn % self.settings.slotframeLength)
                            settlingTime = int((float(self.settings.settlingTime)/float(self.settings.slotDuration)))
                            # experiment time + offset
                            terminationDelay = simTime + offset + settlingTime
                            self.engine.terminateSimulation(terminationDelay)
                            self.engine.asnInitExperiment = self.engine.asn + offset + settlingTime
                            self._log(
                                INFO,
                                "Start experiment set at ASN {0}, end experiment at ASN {1}.",
                                (self.engine.asnInitExperiment, self.engine.asnEndExperiment)
                            )
                            self.engine.startSending()
                        else:
                            cvrgd = [mote.id for mote in self.engine.motes if mote.isConverged == True]
                            self._log(
                                INFO,
                                "{0} motes converged with a dedicated cell in response: {1}.",
                                (len(cvrgd), str(cvrgd))
                            )

                    # update counters
                    if newDir == DIR_TX:
                        if neighbor not in self.numCellsToNeighbors:
                            self.numCellsToNeighbors[neighbor] = 0
                        self.numCellsToNeighbors[neighbor] += len(receivedCellList)
                    elif newDir == DIR_RX:
                        if neighbor not in self.numCellsFromNeighbors:
                            self.numCellsFromNeighbors[neighbor] = 0
                        self.numCellsFromNeighbors[neighbor] += len(receivedCellList)
                    else:
                        if neighbor not in self.numCellsToNeighbors:
                            self.numCellsToNeighbors[neighbor] = 0
                        self.numCellsToNeighbors[neighbor] += len(receivedCellList)
                        if neighbor not in self.numCellsFromNeighbors:
                            self.numCellsFromNeighbors[neighbor] = 0
                        self.numCellsFromNeighbors[neighbor] += len(receivedCellList)

                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                elif code == IANA_6TOP_RC_NORES:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {0} do not have available resources to allocate for node {1}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                    # TODO: increase stats of RC_NORES
                # only when devices are not powerfull enough. Not used in the simulator
                elif code == IANA_6TOP_RC_BUSY:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {0} is busy and do not have available resources for perform another 6top add operation with mote {1}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                    # TODO: increase stats of RC_BUSY
                elif code == IANA_6TOP_RC_RESET:  # should not happen
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {0} has detected an state inconsistency in a 6top add operation with mote {1}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                    # TODO: increase stats of RC_BUSY
                else:
                    assert False

            elif self.sixtopStates[smac.id]['tx']['state'] == SIX_STATE_WAIT_DELETERESPONSE:
                # TODO: now this is still an assert, later this should be handled appropriately
                assert code == IANA_6TOP_RC_SUCCESS or code == IANA_6TOP_RC_NORES or code == IANA_6TOP_RC_RESET

                self._stats_incrementMoteStats('6topRxDelResp')

                neighbor = smac
                receivedCellList = payload[0]
                numCells = payload[1]
                receivedDir = payload[2]
                seq = payload[3]

                # seqNum mismatch, transaction failed, ignore packet
                if seq != self.sixtopStates[neighbor.id]['tx']['seqNum']:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {1} has received a wrong seqNum in a sixtop operation with mote {0}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return False

                # transaction is considered as failed since the timeout has already scheduled for this ASN. Too late for removing the event, ignore packet
                if self.sixtopStates[neighbor.id]['tx']['timer']['asn'] == self.engine.getAsn():
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {1} has received a DELETE response from mote {0} too late',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return False

                # delete the timer.
                uniqueTag = '_sixtop_timer_fired_dest_%s' % neighbor.id
                uniqueTag = (self.id, uniqueTag)
                self.engine.removeEvent(uniqueTag=uniqueTag)

                self._log(
                    INFO,
                    "[6top] removed timer for mote {0} to neighbor {1} on asn {2}, tag {3}",
                    (self.id, neighbor.id, self.sixtopStates[neighbor.id]['tx']['timer']['asn'], str(uniqueTag)),
                )
                del self.sixtopStates[neighbor.id]['tx']['timer']

                self.sixtopStates[smac.id]['tx']['seqNum'] += 1

                # if the request was successfull and there were enough resources
                if code == IANA_6TOP_RC_SUCCESS:
                    # set direction of cells
                    if receivedDir == DIR_TX:
                        newDir = DIR_RX
                    elif receivedDir == DIR_RX:
                        newDir = DIR_TX
                    else:
                        newDir = DIR_TXRX_SHARED

                    assert len(receivedCellList) == 1

                    if self.settings.individualModulations == 1:
                        toDeleteReceivedCellList = []
                        for ts in receivedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] Delete {3} cell ts={0} from {1} to {2}',
                                (ts, self.id, neighbor.id, newDir),
                            )
                            for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                                toDeleteReceivedCellList += [ts + i]

                        self._tsch_removeCells(neighbor, toDeleteReceivedCellList)
                    else:
                        for ts in receivedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] Delete {3} cell ts={0} from {1} to {2}',
                                (ts, self.id, neighbor.id, newDir),
                            )

                        self._tsch_removeCells(neighbor, receivedCellList)

                    # self.numCellsFromNeighbors[neighbor] -= len(receivedCellList)

                    if newDir == DIR_TX:
                        self.numCellsToNeighbors[neighbor] -= len(receivedCellList)
                        assert self.numCellsToNeighbors[neighbor] >= 0
                    elif newDir == DIR_RX:
                        self.numCellsFromNeighbors[neighbor] -= len(receivedCellList)
                        assert self.numCellsFromNeighbors[neighbor] >= 0
                    else:
                        self.numCellsToNeighbors[neighbor] -= len(receivedCellList)
                        assert self.numCellsToNeighbors[neighbor] >= 0
                        self.numCellsFromNeighbors[neighbor] -= len(receivedCellList)
                        assert self.numCellsFromNeighbors[neighbor] >= 0

                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []
                    return True
                elif code == IANA_6TOP_RC_NORES:
                    # log
                    self._log(
                        INFO,
                        '[6top] The resources requested for delete were not available for {1} in {0}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                    # TODO: increase stats of RC_NORES
                # only when devices are not powerfull enough. Not used in the simulator
                elif code == IANA_6TOP_RC_BUSY:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {0} is busy and has not available resources for perform another 6top deletion operation with mote {1}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    return True
                    # TODO: increase stats of RC_BUSY
                elif code == IANA_6TOP_RC_RESET:
                    # log
                    self._log(
                        INFO,
                        '[6top] The node {0} has detected an state inconsistency in a 6top deletion operation with mote {1}',
                        (neighbor.id, self.id),
                    )
                    # go back to IDLE, i.e. remove the neighbor form the states
                    self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                    self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []

                    # TODO: increase stats of RC_RESET
                    return True
                else:  # should not happen
                    assert False
            else:
                # only ADD and DELETE implemented so far
                # do not do an assert because it can be you come here if a timer expires
                # assert False
                pass

    def _sixtop_receive_RESPONSE_ACK(self, packet):
        with self.dataLock:

            if self.sixtopStates[packet['dstIp'].id]['rx']['state'] == SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE:

                confirmedCellList = packet['payload'][0]
                receivedDir = packet['payload'][2]
                neighbor = packet['dstIp']
                code = packet['code']

                self._stats_logSixTopLatencyStat(self.engine.asn - self.tsSixTopReqRecv[neighbor])
                self.tsSixTopReqRecv[neighbor] = 0

                if code == IANA_6TOP_RC_SUCCESS:
                    if self.settings.individualModulations == 1:
                        cellList = []
                        parentTs = None
                        first = True
                        assert len(confirmedCellList) == 1
                        for (ts, ch, cellDir) in confirmedCellList:
                            if first:
                                parentTs = ts
                                first = False
                            # log
                            self._log(
                                INFO,
                                '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                (ts, ch, self.id, neighbor.id, cellDir),
                            )
                            # TODO save the modulation somewhere and not take it in a godlike manner!
                            for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                                cellList += [(ts + i, ch, cellDir)]
                                self._log(
                                    INFO,
                                    '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                    (ts + i, ch, self.id, neighbor.id, cellDir),
                                )
                        self._tsch_addCells(neighbor, cellList, parentTs=parentTs, modulation=self.modulation[neighbor])
                    else:
                        for (ts, ch, cellDir) in confirmedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                                (ts, ch, self.id, neighbor.id, cellDir),
                            )
                        self._tsch_addCells(neighbor, confirmedCellList)

                    # update counters
                    if receivedDir == DIR_TX:
                        if neighbor not in self.numCellsToNeighbors:
                            self.numCellsToNeighbors[neighbor] = 0
                        self.numCellsToNeighbors[neighbor] += len(confirmedCellList)
                    elif receivedDir == DIR_RX:
                        if neighbor not in self.numCellsFromNeighbors:
                            self.numCellsFromNeighbors[neighbor] = 0
                        self.numCellsFromNeighbors[neighbor] += len(confirmedCellList)
                    else:
                        if neighbor not in self.numCellsToNeighbors:
                            self.numCellsToNeighbors[neighbor] = 0
                        self.numCellsToNeighbors[neighbor] += len(confirmedCellList)
                        if neighbor not in self.numCellsFromNeighbors:
                            self.numCellsFromNeighbors[neighbor] = 0
                        self.numCellsFromNeighbors[neighbor] += len(confirmedCellList)

                # go back to IDLE, i.e. remove the neighbor form the states
                # but if the node received another, already new request, from the same node (because its timer fired), do not go to IDLE
                self.sixtopStates[neighbor.id]['rx']['state'] = SIX_STATE_IDLE
                self.sixtopStates[neighbor.id]['rx']['blockedCells'] = []
                self.sixtopStates[neighbor.id]['rx']['seqNum'] += 1

            elif self.sixtopStates[packet['dstIp'].id]['rx']['state'] == SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE:

                confirmedCellList = packet['payload'][0]
                receivedDir = packet['payload'][2]
                neighbor = packet['dstIp']
                code = packet['code']

                self._stats_logSixTopLatencyStat(self.engine.asn - self.tsSixTopReqRecv[neighbor])
                self.tsSixTopReqRecv[neighbor] = 0

                if code == IANA_6TOP_RC_SUCCESS:
                    if self.settings.individualModulations == 1:
                        toDeleteReceivedCellList = []
                        assert len(confirmedCellList) == 1
                        for ts in confirmedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] delete {3} cell ts={0} from {1} to {2}',
                                (ts, self.id, neighbor.id, receivedDir),
                            )
                            for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][self.modulation[neighbor]]):
                                toDeleteReceivedCellList += [ts + i]

                        self._tsch_removeCells(neighbor, toDeleteReceivedCellList)
                    else:
                        for ts in confirmedCellList:
                            # log
                            self._log(
                                INFO,
                                '[6top] delete {3} cell ts={0} from {1} to {2}',
                                (ts, self.id, neighbor.id, receivedDir),
                            )
                        self._tsch_removeCells(neighbor, confirmedCellList)

                    # update counters
                    if receivedDir == DIR_TX:
                        self.numCellsToNeighbors[neighbor] -= len(confirmedCellList)
                        assert self.numCellsToNeighbors[neighbor] >= 0
                    elif receivedDir == DIR_RX:
                        self.numCellsFromNeighbors[neighbor] -= len(confirmedCellList)
                        assert self.numCellsFromNeighbors[neighbor] >= 0
                    else:
                        self.numCellsToNeighbors[neighbor] -= len(confirmedCellList)
                        assert self.numCellsToNeighbors[neighbor] >= 0
                        self.numCellsFromNeighbors[neighbor] -= len(confirmedCellList)
                        assert self.numCellsFromNeighbors[neighbor] >= 0

                    # self.numCellsFromNeighbors[neighbor] -= len(confirmedCellList)
                    # assert self.numCellsFromNeighbors[neighbor] >= 0

                # go back to IDLE, i.e. remove the neighbor form the states
                self.sixtopStates[neighbor.id]['rx']['state'] = SIX_STATE_IDLE
                self.sixtopStates[neighbor.id]['rx']['blockedCells'] = []
                self.sixtopStates[neighbor.id]['rx']['seqNum'] += 1

            else:
                # only add and delete are implemented so far
                assert False

    def _sixtop_cell_deletion_sender(self, neighbor, tsList, dir, timeout):
        with self.dataLock:
            if self.settings.sixtopMessaging:
                if neighbor.id not in self.sixtopStates or (
                        neighbor.id in self.sixtopStates and 'tx' in self.sixtopStates[neighbor.id] and
                        self.sixtopStates[neighbor.id]['tx']['state'] == SIX_STATE_IDLE):

                    # if neighbor not yet in states dict, add it
                    if neighbor.id not in self.sixtopStates:
                        self.sixtopStates[neighbor.id] = {}
                    if 'tx' not in self.sixtopStates:
                        self.sixtopStates[neighbor.id]['tx'] = {}
                        self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[neighbor.id]['tx']['blockedCells'] = []
                        self.sixtopStates[neighbor.id]['tx']['seqNum'] = 0
                    self.sixtopStates[neighbor.id]['tx']['timeout'] = timeout

                    self._sixtop_enqueue_DELETE_REQUEST(neighbor, tsList, len(tsList), dir,
                                                        self.sixtopStates[neighbor.id]['tx']['seqNum'])
                else:
                    self._log(
                        DEBUG,
                        "[6top] can not send 6top DELETE request to {0} because timer still did not fire on mote {1}.",
                        (neighbor.id, self.id),
                    )

            else:
                # log
                self._log(
                    INFO,
                    "[6top] remove timeslots={0} with {1}",
                    (tsList, neighbor.id),
                )
                self._tsch_removeCells(
                    neighbor=neighbor,
                    tsList=tsList,
                )

                newDir = DIR_RX
                if dir == DIR_TX:
                    newDir = DIR_RX
                elif dir == DIR_RX:
                    newDir = DIR_TX
                else:
                    newDir = DIR_TXRX_SHARED

                neighbor._sixtop_cell_deletion_receiver(self, tsList, newDir)

                # update counters
                if dir == DIR_TX:
                    self.numCellsToNeighbors[neighbor] -= len(tsList)
                elif dir == DIR_RX:
                    self.numCellsFromNeighbors[neighbor] -= len(tsList)
                else:
                    self.numCellsToNeighbors[neighbor] -= len(tsList)
                    self.numCellsFromNeighbors[neighbor] -= len(tsList)

                assert self.numCellsToNeighbors[neighbor] >= 0

    def _sixtop_cell_deletion_receiver(self, neighbor, tsList, dir):
        with self.dataLock:
            self._tsch_removeCells(
                neighbor=neighbor,
                tsList=tsList,
            )
            # update counters
            if dir == DIR_TX:
                self.numCellsToNeighbors[neighbor] -= len(tsList)
            elif dir == DIR_RX:
                self.numCellsFromNeighbors[neighbor] -= len(tsList)
            else:
                self.numCellsToNeighbors[neighbor] -= len(tsList)
                self.numCellsFromNeighbors[neighbor] -= len(tsList)
            assert self.numCellsFromNeighbors[neighbor] >= 0

    def _sixtop_removeCells(self, neighbor, numCellsToRemove, dir, timeout):
        """
        Finds cells to neighbor, and remove it.
        """

        # get cells to the neighbors
        scheduleList = []

        # remove a cell based on ellsf's algorithm
        # check below that you can only delete non-resf cells
        # how can the minimal cell not be removed?

        # if self.eLLSF is not None:
        #
        #     rxTimeslots = []
        #     txTimeslots = []
        #     if neighbor == self.preferredParent:
        #         # by making sure ts is in ELLSF_TIMESLOTS, we make sure we only delete eLLSF cells, and we also avoid the minimal cell
        #         rxTimeslots = [ts for (ts, cell) in self.schedule.iteritems() if
        #                        cell['dir'] == DIR_TXRX_SHARED and cell[
        #                            'neighbor'] != self.preferredParent and ts in self.eLLSF.ELLSF_TIMESLOTS and not
        #                        cell['resf']]
        #         txTimeslots = [ts for (ts, cell) in self.schedule.iteritems() if
        #                        cell['dir'] == DIR_TXRX_SHARED and cell[
        #                            'neighbor'] == self.preferredParent and ts in self.eLLSF.ELLSF_TIMESLOTS and not
        #                        cell['resf']]
        #     elif neighbor != self.preferredParent and not self._isBroadcast(neighbor):  # any other cell except a broadcast
        #         # because now we only look at SHARED cells, tx and rx timeslots are the same, so basically we are removing the SHARED cell with the largest gap to its left
        #         rxTimeslots = [ts for (ts, cell) in self.schedule.iteritems() if
        #                        cell['dir'] == DIR_TXRX_SHARED and cell[
        #                            'neighbor'] == neighbor and ts in self.eLLSF.ELLSF_TIMESLOTS and not cell['resf']]
        #         txTimeslots = [ts for (ts, cell) in self.schedule.iteritems() if
        #                        cell['dir'] == DIR_TXRX_SHARED and cell[
        #                            'neighbor'] == neighbor and ts in self.eLLSF.ELLSF_TIMESLOTS and not cell['resf']]
        #     elif self._isBroadcast(neighbor):  # broadcast cell
        #         assert False;
        #     else:  # don't know what to expect
        #         assert False
        #
        #     txTsDistance = []
        #     for i in range(len(txTimeslots)):
        #         distance = 1000  # big value
        #         for j in range(len(rxTimeslots)):
        #             if txTimeslots[i] > rxTimeslots[j]:
        #                 if txTimeslots[i] - rxTimeslots[j] < distance:
        #                     distance = txTimeslots[i] - rxTimeslots[j]
        #             else:
        #                 if self.settings.slotframeLength + txTimeslots[i] - rxTimeslots[j] < distance:
        #                     distance = self.settings.slotframeLength + txTimeslots[i] - rxTimeslots[j]
        #         txTsDistance.append((txTimeslots[i], distance))
        #
        #     if len(rxTimeslots) > 0:
        #         txTsDistance.sort(key=lambda x: x[1], reverse=True)
        #     else:  # eg, when in a leaf node, there are no children, just delete a random one
        #         self.genMSF.shuffle(txTsDistance)
        #
        #     for i in range(len(txTsDistance)):
        #         numTxAck = self.schedule[txTsDistance[i][0]]['numTxAck']
        #         numTx = self.schedule[txTsDistance[i][0]]['numTx']
        #         cellPDR = self.getCellPDR(self.schedule[txTsDistance[i][0]])
        #         scheduleList += [(txTsDistance[i][0], numTxAck, numTx, cellPDR)]
        #
        # else:
            # worst cell removing initialized by theoretical pdr
        for (ts, cell) in self.schedule.iteritems():
            # only remove the cell where ts == parentTs, the other ones will be removed automatically
            if cell['parentTs'] == ts and ((cell['neighbor'] == neighbor and cell['dir'] == DIR_TX) or (cell['dir'] == DIR_TXRX_SHARED and cell['neighbor'] == neighbor)):
                cellPDR = self.getCellPDR(cell)
                scheduleList += [(ts, cell['numTxAck'], cell['numTx'], cellPDR)]

        if self.settings.sixtopRemoveRandomCell:
            # introduce randomness in the cell list order
            self.genMSF.shuffle(scheduleList)
        else:
            # triggered only when worst cell selection is due
            # (cell list is sorted according to worst cell selection)
            scheduleListByPDR = {}
            for tscell in scheduleList:
                if not tscell[3] in scheduleListByPDR:
                    scheduleListByPDR[tscell[3]] = []
                scheduleListByPDR[tscell[3]] += [tscell]
            rssi = self.getRSSI(neighbor)
            modulation = None
            if self.settings.individualModulations == 1:
                modulation = self.modulation[neighbor]
            # theoPDR = Topology.Topology.rssiToPdr(rssi, modulation=modulation)
            theoPDR = self.getPDR(neighbor)
            scheduleList = []
            for pdr in sorted(scheduleListByPDR.keys()):
                if pdr < theoPDR:
                    scheduleList += sorted(scheduleListByPDR[pdr], key=lambda x: x[2], reverse=True)
                else:
                    scheduleList += sorted(scheduleListByPDR[pdr], key=lambda x: x[2])

        # remove a given number of cells from the list of available cells (picks the first numCellToRemove)
        tsList = []
        for tscell in scheduleList[:numCellsToRemove]:
            # log
            self._log(
                INFO,
                "[6top] remove cell ts={0} to {1} (pdr={2:.3f})",
                (tscell[0], neighbor.id, tscell[3]),
            )
            tsList += [tscell[0]]

        assert len(tsList) == numCellsToRemove

        # remove cells
        self._sixtop_cell_deletion_sender(neighbor, tsList, dir, timeout)

    def _sixtop_enqueue_DELETE_REQUEST(self, neighbor, cellList, numCells, dir, seq):
        """ enqueue a new 6P DELETE request """

        self._log(
            INFO,
            '[6top] enqueueing a new 6P DEL message cellList={0}, numCells={1} from {2} to {3}',
            (cellList, numCells, self.id, neighbor.id),
        )

        # create new packet
        newPacket = {
            'asn': self.engine.getAsn(),
            'type': IANA_6TOP_TYPE_REQUEST,
            'code': IANA_6TOP_CMD_DELETE,
            'payload': [cellList, numCells, dir, seq, self.engine.getAsn()],
            'retriesLeft': TSCH_MAXTXRETRIES,
            'srcIp': self,
            'dstIp': neighbor,  # currently upstream
            'sourceRoute': [],
        }

        # enqueue packet in TSCH queue
        isEnqueued = self._tsch_enqueue(newPacket)

        if not isEnqueued:

            # update mote stats
            self._radio_drop_packet(newPacket, 'droppedFailedEnqueue')

        else:
            # set state to sending request for this neighbor
            self.sixtopStates[neighbor.id]['tx']['state'] = SIX_STATE_SENDING_REQUEST

    def _sixtop_receive_DELETE_REQUEST(self, type, smac, payload):
        """ receive a 6P delete request message """
        with self.dataLock:
            neighbor = smac
            cellList = payload[0]
            numCells = payload[1]
            receivedDir = payload[2]
            seq = payload[3]

            self._stats_incrementMoteStats('6topRxDelReq')
            # has the asn of when the req packet was enqueued in the neighbor. Used for calculate avg 6top latency
            self.tsSixTopReqRecv[neighbor] = payload[4]

            if smac.id in self.sixtopStates and 'rx' in self.sixtopStates[smac.id] and self.sixtopStates[smac.id]['rx']['state'] != SIX_STATE_IDLE:
                for pkt in self.txQueue:
                    if pkt['type'] == IANA_6TOP_TYPE_RESPONSE and pkt['dstIp'].id == smac.id:
                        self.txQueue.remove(pkt)
                        self._log(
                            INFO,
                            "[6top] removed a 6TOP_TYPE_RESPONSE packet in the queue of mote {0} to neighbor {1}, because a new TYPE_REQUEST (delete) was received.",
                            (self.id, smac.id),
                        )
                        # assert False
                returnCode = IANA_6TOP_RC_RESET  # error, neighbor has to abort transaction
                if smac.id not in self.sixtopStates:
                    self.sixtopStates[smac.id] = {}
                if 'rx' not in self.sixtopStates:
                    self.sixtopStates[smac.id]['rx'] = {}
                    self.sixtopStates[smac.id]['rx']['blockedCells'] = []
                    self.sixtopStates[smac.id]['rx']['seqNum'] = 0
                self.sixtopStates[smac.id]['rx']['state'] = SIX_STATE_REQUEST_DELETE_RECEIVED
                self._sixtop_enqueue_RESPONSE(neighbor, [], returnCode, receivedDir, seq)

                return

            # set state to receiving request for this neighbor
            if smac.id not in self.sixtopStates:
                self.sixtopStates[smac.id] = {}
            if 'rx' not in self.sixtopStates[neighbor.id]:
                self.sixtopStates[smac.id]['rx'] = {}
                self.sixtopStates[smac.id]['rx']['blockedCells'] = []
                self.sixtopStates[smac.id]['rx']['seqNum'] = 0
                # if neighbor is not in sixtopstates and receives a delete, something has gone wrong. Send a RESET.
                returnCode = IANA_6TOP_RC_RESET  # error, neighbor has to abort transaction
                assert False
                self._sixtop_enqueue_RESPONSE(neighbor, [], returnCode, receivedDir, seq)

                return

            self.sixtopStates[smac.id]['rx']['state'] = SIX_STATE_REQUEST_DELETE_RECEIVED

            # set direction of cells
            if receivedDir == DIR_TX:
                newDir = DIR_RX
            elif receivedDir == DIR_RX:
                newDir = DIR_TX
            else:
                newDir = DIR_TXRX_SHARED

            returnCode = IANA_6TOP_RC_SUCCESS  # all is fine

            for cell in cellList:
                if cell not in self.schedule.keys():
                    returnCode = IANA_6TOP_RC_NORES  # resources are not present

            # enqueue response
            self._sixtop_enqueue_RESPONSE(neighbor, cellList, returnCode, newDir, seq)

    # ===== tsch

    # BROADCAST cells
    def _tsch_resetBroadcastBackoff(self):
        self.backoffBroadcast = 0
        # self.backoffBroadcastExponent = self.settings.backoffMinExp - 1
        self.backoffBroadcastExponent = 2 - 1

    # SHARED Dedicated cells
    def _tsch_resetBackoffPerNeigh(self, neigh):
        self.backoffPerNeigh[neigh] = 0
        self.backoffExponentPerNeigh[neigh] = self.settings.backoffMinExp - 1

    def _tsch_enqueue(self, packet):

        if not self._rpl_addNextHop(packet):
            # I don't have a route

            # increment mote state
            self._stats_incrementMoteStats('droppedNoRoute')
            return False

        elif not (self.getTxCells() or self.getSharedCells()):
            # I don't have any transmit cells

            # increment mote state
            self._stats_incrementMoteStats('droppedNoTxCells')

            if self.settings.sf != 'ilp':
                assert False

            return False

        elif len(self.txQueue) >= TSCH_QUEUE_SIZE:
            # my TX queue is full.

            # However, I will allow to add an additional packet in some specific ocasions
            # This is because if the queues of the nodes are filled with DATA packets, new nodes won't be able to enter properly in the network. So there are exceptions.

            # if join is enabled, all nodes will wait until all nodes have at least 1 Tx cell. So it is allowed to enqueue 1 aditional DAO, JOIN or 6P packet
            if packet['type'] == APP_TYPE_JOIN or packet['type'] == RPL_TYPE_DAO or packet[
                'type'] == IANA_6TOP_TYPE_REQUEST or packet['type'] == IANA_6TOP_TYPE_RESPONSE:
                for p in self.txQueue:
                    if packet['type'] == p['type']:
                        # There is already a DAO, JOIN or 6P in que queue, don't add more
                        self._stats_incrementMoteStats('droppedQueueFull')
                        return False
                self.txQueue += [packet]
                return True

            # update mote stats
            self._stats_incrementMoteStats('droppedQueueFull')

            return False

        else:
            # all is good

            # enqueue packet
            self.txQueue += [packet]

            return True

    def _tsch_schedule_activeCell(self):

        asn = self.engine.getAsn()
        tsCurrent = asn % self.settings.slotframeLength

        # find closest active slot in schedule
        with self.dataLock:

            if not self.schedule:
                self.engine.removeEvent(uniqueTag=(self.id, '_tsch_action_activeCell'))
                return

            tsDiffMin = None
            for (ts, cell) in self.schedule.items():
                if ts == tsCurrent:
                    tsDiff = self.settings.slotframeLength
                elif ts > tsCurrent:
                    tsDiff = ts - tsCurrent
                elif ts < tsCurrent:
                    tsDiff = (ts + self.settings.slotframeLength) - tsCurrent
                else:
                    raise SystemError()

                if (not tsDiffMin) or (tsDiffMin > tsDiff):
                    tsDiffMin = tsDiff

        # schedule at that ASN
        self.engine.scheduleAtAsn(
            asn=asn + tsDiffMin,
            cb=self._tsch_action_activeCell,
            uniqueTag=(self.id, '_tsch_action_activeCell'),
            priority=0,
        )

    def _tsch_action_activeCell(self):
        """
        active slot starts. Determine what todo, either RX or TX, use the propagation model to introduce
        interference and Rx packet drops.
        """

        asn = self.engine.getAsn()
        ts = asn % self.settings.slotframeLength

        with self.dataLock:

            # make sure this is an active slot
            assert ts in self.schedule

            if self.settings.individualModulations == 0:
                # make sure we're not in the middle of a TX/RX operation
                assert not self.waitingFor

            cell = self.schedule[ts]

            # only if this does not belong to another cell, than you can use it
            if cell['parentTs'] is None or (cell['parentTs'] is not None and cell['parentTs'] == ts):

                if self.settings.individualModulations == 1:
                    # make sure we're not in the middle of a TX/RX operation
                    assert not self.waitingFor

                # Signal to MSF that a cell to a neighbor has been triggered
                if self._msf_is_enabled():
                    self._msf_signal_cell_elapsed(cell['neighbor'], cell['dir'])

                if cell['dir'] == DIR_RX:

                    aggregatedInfo = None
                    if self.settings.individualModulations == 1 and cell['parentTs'] is not None:
                        aggregatedInfo = {'startSlot': cell['parentTs'], \
                                          'endSlot': (cell['parentTs'] + Modulation.Modulation().modulationSlots[self.settings.modulationConfig][
                                              cell['modulation']] - 1), \
                                          'modulation': cell['modulation'], \
                                          'success': True, \
                                          'packetSize': self.settings.packetSize, \
                                          'interferers': []}

                    # start listening
                    self.propagation.startRx(
                        mote=self,
                        channel=cell['ch'],
                        aggregatedInfo=aggregatedInfo
                    )
                    self.onGoingReception = True

                    # indicate that we're waiting for the RX operation to finish
                    self.waitingFor = DIR_RX

                elif cell['dir'] == DIR_TX:
                    # check whether packet to send
                    self.pktToSend = None
                    if self.txQueue:
                        for pkt in self.txQueue:
                            # send the frame if next hop matches the cell destination
                            if pkt['nextHop'] == [cell['neighbor']]:
                                self.pktToSend = pkt
                                break

                    # send packet
                    if self.pktToSend:

                        # Signal to MSF that a cell to a neighbor is used
                        if self._msf_is_enabled():
                            self._msf_signal_cell_used(cell['neighbor'], cell['dir'], DIR_TX, pkt['type'])

                        cell['numTx'] += 1

                        if pkt['type'] == IANA_6TOP_TYPE_REQUEST:
                            if pkt['code'] == IANA_6TOP_CMD_ADD:
                                self._stats_incrementMoteStats('6topTxAddReq')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxAddReq += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxAddReq += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['tx'][
                                    'state'] = SIX_STATE_WAIT_ADDREQUEST_SENDDONE
                            elif pkt['code'] == IANA_6TOP_CMD_DELETE:
                                self._stats_incrementMoteStats('6topTxDelReq')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxDelReq += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxDelReq += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['tx'][
                                    'state'] = SIX_STATE_WAIT_DELETEREQUEST_SENDDONE
                            else:
                                assert False

                        if pkt['type'] == RPL_TYPE_DAO:
                            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                self.activeDAO += 1
                            elif not self.settings.convergeFirst:
                                self.activeDAO += 1

                        if pkt['type'] == IANA_6TOP_TYPE_RESPONSE:
                            if self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                'state'] == SIX_STATE_REQUEST_ADD_RECEIVED:
                                self._stats_incrementMoteStats('6topTxAddResp')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxAddResp += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxAddResp += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                    'state'] = SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                'state'] == SIX_STATE_REQUEST_DELETE_RECEIVED:
                                self._stats_incrementMoteStats('6topTxDelResp')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxDelResp += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxDelResp += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                    'state'] = SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                'state'] == SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE:
                                pass
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx'][
                                'state'] == SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE:
                                pass
                            else:
                                assert False

                        aggregatedInfo = None
                        if self.settings.individualModulations == 1 and cell['parentTs'] is not None:
                            aggregatedInfo = {'startSlot': cell['parentTs'], \
                                                  'endSlot': (cell['parentTs'] + Modulation.Modulation().modulationSlots[self.settings.modulationConfig][cell['modulation']] - 1), \
                                                  'modulation': cell['modulation'], \
                                                  'success': True, \
                                                  'packetSize': self.settings.packetSize, \
                                                  'interferers': []}

                        self.propagation.startTx(
                            channel=cell['ch'],
                            type=self.pktToSend['type'],
                            code=self.pktToSend['code'],
                            smac=self,
                            dmac=[cell['neighbor']],
                            srcIp=self.pktToSend['srcIp'],
                            dstIp=self.pktToSend['dstIp'],
                            srcRoute=self.pktToSend['sourceRoute'],
                            payload=self.pktToSend['payload'],
                            aggregatedInfo=aggregatedInfo
                        )

                        # indicate that we're waiting for the TX operation to finish
                        self.waitingFor = DIR_TX

                    # else:
                    #     if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    #         if self.id not in self.engine.comehere:
                    #             self.engine.comehere[self.id] = 1
                    #         else:
                    #             self.engine.comehere[self.id] += 1
                    # else:
                    #     if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    #         self.nrNoTxDataRxAck += [ts]
                    #     elif not self.settings.convergeFirst:
                    #         self.nrNoTxDataRxAck += [ts]

                elif cell['dir'] == DIR_TXRX_SHARED:
                    # if cell['neighbor'] == self._myNeighbors():
                    assert False
                    if self._isBroadcast(cell['neighbor']):
                        self.pktToSend = None
                        if self.txQueue and self.backoffBroadcast == 0:
                            for pkt in self.txQueue:
                                # send join packets on the shared cell only on first hop
                                if pkt['type'] == APP_TYPE_JOIN and len(
                                        self.getTxCells(neighbor=pkt['nextHop'][0])) + len(
                                        self.getSharedCells(neighbor=pkt['nextHop'][0])) == 0:
                                    self.pktToSend = pkt
                                    break
                                # send 6P messages on the shared broadcast cell only if there is no dedicated cells to that neighbor
                                elif pkt['type'] == IANA_6TOP_TYPE_REQUEST and len(
                                        self.getTxCells(neighbor=pkt['nextHop'][0])) + len(
                                        self.getSharedCells(neighbor=pkt['nextHop'][0])) == 0:
                                    self.pktToSend = pkt
                                    break
                                # send 6P messages on the shared broadcast cell only if there is no dedicated cells to that neighbor
                                elif pkt['type'] == IANA_6TOP_TYPE_RESPONSE and len(
                                        self.getTxCells(neighbor=pkt['nextHop'][0])) + len(
                                        self.getSharedCells(neighbor=pkt['nextHop'][0])) == 0:
                                    self.pktToSend = pkt
                                    break
                                # DIOs and EBs always go on the shared broadcast cell
                                elif pkt['type'] == RPL_TYPE_DIO or pkt['type'] == TSCH_TYPE_EB:
                                    self.pktToSend = pkt
                                    break
                                else:
                                    continue
                        # Decrement backoff
                        if self.backoffBroadcast > 0:
                            self.backoffBroadcast -= 1
                    else:
                        if self.isSync:
                            # check whether packet to send
                            self.pktToSend = None
                            if self.txQueue and self.backoffPerNeigh[cell['neighbor']] == 0:
                                for pkt in self.txQueue:
                                    # send the frame if next hop matches the cell destination
                                    if pkt['nextHop'] == [cell['neighbor']] and pkt['dstIp'] != BROADCAST_ADDRESS:
                                        self.pktToSend = pkt
                                        break


                        # if self.pktToSend is None and self.txQueue and self.backoffPerNeigh[cell['neighbor']] > 0:
                        #     for pkt in self.txQueue:
                        #         # send the frame if next hop matches the cell destination
                        #         if pkt['nextHop'] == [cell['neighbor']]:
                        #             self._msf_signal_cell_used(cell['neighbor'], cell['dir'], DIR_TX, pkt['type'])
                        #             break

                        # Decrement backoffPerNeigh
                        if self.backoffPerNeigh[cell['neighbor']] > 0:
                            self.backoffPerNeigh[cell['neighbor']] -= 1
                            self._log(
                                    INFO,
                                    "[tsch] in ts {2} to neighbor {3}:  decrementing from {0} to {1}",
                                (self.backoffPerNeigh[cell['neighbor']] + 1, self.backoffPerNeigh[cell['neighbor']], ts, cell['neighbor'].id)
                                )

                    # send packet
                    if self.pktToSend:

                        cell['numTx'] += 1

                        # Signal to MSF that a cell to a neighbor is used
                        if self._msf_is_enabled():
                            self._msf_signal_cell_used(cell['neighbor'], cell['dir'], DIR_TX, pkt['type'])

                        if pkt['type'] == IANA_6TOP_TYPE_REQUEST:
                            if pkt['code'] == IANA_6TOP_CMD_ADD:
                                self._stats_incrementMoteStats('6topTxAddReq')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxAddReq += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxAddReq += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['tx'][
                                    'state'] = SIX_STATE_WAIT_ADDREQUEST_SENDDONE
                            elif pkt['code'] == IANA_6TOP_CMD_DELETE:
                                self._stats_incrementMoteStats('6topTxDelReq')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxDelReq += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxDelReq += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['tx']['state'] = SIX_STATE_WAIT_DELETEREQUEST_SENDDONE
                            else:
                                assert False

                        if pkt['type'] == IANA_6TOP_TYPE_RESPONSE:
                            if self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] == SIX_STATE_REQUEST_ADD_RECEIVED:
                                self._stats_incrementMoteStats('6topTxAddResp')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxAddResp += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxAddResp += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] = SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] == SIX_STATE_REQUEST_DELETE_RECEIVED:
                                self._stats_incrementMoteStats('6topTxDelResp')

                                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                    self.sixtopTxDelResp += 1
                                elif not self.settings.convergeFirst:
                                    self.sixtopTxDelResp += 1

                                self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] = SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] == SIX_STATE_WAIT_ADD_RESPONSE_SENDDONE:
                                pass
                            elif self.sixtopStates[self.pktToSend['nextHop'][0].id]['rx']['state'] == SIX_STATE_WAIT_DELETE_RESPONSE_SENDDONE:
                                pass
                            else:
                                assert False

                        if pkt['type'] == RPL_TYPE_DAO:
                            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                                self.activeDAO += 1
                            elif not self.settings.convergeFirst:
                                self.activeDAO += 1

                        aggregatedInfo = None
                        if self.settings.individualModulations == 1 and cell['parentTs'] is not None:
                            aggregatedInfo = {'startSlot': cell['parentTs'], \
                                                  'endSlot': (cell['parentTs'] + Modulation.Modulation().modulationSlots[self.settings.modulationConfig][cell['modulation']] - 1), \
                                                  'modulation': cell['modulation'], \
                                                  'success': True, \
                                                  'packetSize': self.settings.packetSize, \
                                                  'interferers': []}

                        self.propagation.startTx(
                            channel=cell['ch'],
                            type=self.pktToSend['type'],
                            code=self.pktToSend['code'],
                            smac=self,
                            dmac=self.pktToSend['nextHop'],
                            srcIp=self.pktToSend['srcIp'],
                            dstIp=self.pktToSend['dstIp'],
                            srcRoute=self.pktToSend['sourceRoute'],
                            payload=self.pktToSend['payload'],
                            aggregatedInfo=aggregatedInfo
                        )
                        self.waitingFor = DIR_TX

                    else:
                        aggregatedInfo = None
                        if self.settings.individualModulations == 1 and cell['parentTs'] is not None:
                            aggregatedInfo = {'startSlot': cell['parentTs'], \
                                              'endSlot': (cell['parentTs'] + Modulation.Modulation().modulationSlots[self.settings.modulationConfig][cell['modulation']] - 1), \
                                              'modulation': cell['modulation'], \
                                              'success': True, \
                                              'packetSize': self.settings.packetSize, \
                                              'interferers': []}
                        # start listening
                        self.propagation.startRx(
                            mote=self,
                            channel=cell['ch'],
                            aggregatedInfo=aggregatedInfo
                        )

                        # indicate that we're waiting for the RX operation to finish
                        self.waitingFor = DIR_RX

            # schedule next active cell
            self._tsch_schedule_activeCell()

    def getMote(self, id):
        for m in self.engine.motes:
            if m.id == id:
                return m
        assert False

    def _ilp_tsch_addCells(self, sigmaList):
        print 'ILP adding for mote %s' % self
        print sigmaList
        for (ts, ch, cell_dir, neighbor_id, mcs, slots) in sigmaList:
            neighbor = self.getMote(neighbor_id) # get the actual neighbor mapping to the ID
            # if the direction is TX, than the neighbor has to be the preferred parent
            # if cell_dir == DIR_TX and neighbor != self.preferredParent:
            #     assert False
            # if the modulation is not a know modulation, assert
            if mcs not in Modulation.Modulation().allowedModulations[self.settings.modulationConfig]:
                assert False
            # the number of slots given by the ILP for the mcs should match the number by our Modulation config
            if slots != Modulation.Modulation().modulationSlots[self.settings.modulationConfig][mcs]:
                print slots
                print Modulation.Modulation().modulationSlots[self.settings.modulationConfig][mcs]
                assert False
            parent_timeslot = None
            first = True
            cell_list = []
            if first:
                parent_timeslot = ts
                first = False
            # print 'Neighbor preferred parent is {0}'.format(neighbor.preferredParent.id)
            if neighbor is self.preferredParent:
                if neighbor not in self.numCellsToNeighbors:
                    self.numCellsToNeighbors[neighbor] = 0
                self.numCellsToNeighbors[neighbor] += 1
            elif self is neighbor.preferredParent:
                if neighbor not in self.numCellsFromNeighbors:
                    self.numCellsFromNeighbors[neighbor] = 0
                self.numCellsFromNeighbors[neighbor] += 1
            else:
                assert False # it should be one of the above

            for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][mcs]):
                cell_list += [(ts + i, ch, cell_dir)]
                self._log(
                    INFO,
                    '[ILP - 6top] add {4} cell ts={0},ch={1} from {2} to {3}',
                    (ts + i, ch, self.id, neighbor.id, cell_dir),
                )
            # add this the cell
            self._tsch_addCells(neighbor, cell_list, parentTs=parent_timeslot, modulation=mcs)

    def _tsch_addCells(self, neighbor, cellList, parentTs=None, modulation=None):
        """ adds cell(s) to the schedule """

        with self.dataLock:
            for cell in cellList:
                assert cell[0] not in self.schedule.keys()
                self.schedule[cell[0]] = {
                    'ch': cell[1],
                    'dir': cell[2],
                    'neighbor': neighbor,
                    'numTx': 0,
                    'numTxAck': 0,
                    'numRx': 0,
                    'history': [],
                    'sharedCellSuccess': 0,  # indicator of success for shared cells
                    'sharedCellCollision': 0,  # indicator of a collision for shared cells
                    'rxDetectedCollision': False,
                    'debug_canbeInterfered': [],
                # [debug] shows schedule collision that can be interfered with minRssi or larger level
                    'debug_interference': [],  # [debug] shows an interference packet with minRssi or larger level
                    'debug_lockInterference': [],  # [debug] shows locking on the interference packet
                    'debug_cellCreatedAsn': self.engine.getAsn(),  # [debug]
                    'parentTs': parentTs,
                    'modulation': modulation
                }
                # log
                # self._log(
                #     INFO,
                #     "[tsch] add cell ts={0} ch={1} dir={2} with {3} (and backupDuration {4})",
                #     (cell[0], cell[1], cell[2], neighbor.id if not type(neighbor) == list else BROADCAST_ADDRESS, str(backupDuration))),
                # )
            self._tsch_schedule_activeCell()

    def _tsch_removeCells(self, neighbor, tsList):
        """ removes cell(s) from the schedule """

        with self.dataLock:
            for cell in tsList:
                assert type(cell) == int
                # log
                self._log(
                    INFO,
                    "[tsch] remove cell=({0}) with {1}",
                    (cell, neighbor.id if not type(neighbor) == list else BROADCAST_ADDRESS),
                )

                assert cell in self.schedule.keys()
                assert self.schedule[cell]['neighbor'] == neighbor

                self.schedule.pop(cell)

                # if cell <= self.engine.asn % self.settings.slotframeLength:
                #     # you should not count this cell for the sleep slots
                #     if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                #         self.nrRemovedCells += 1
                #     elif not self.settings.convergeFirst:
                #         self.nrRemovedCells += 1


            self._tsch_schedule_activeCell()

    def _tsch_updateMinimalCells(self):
        """ adds cell(s) to the schedule """

        with self.dataLock:
            for c in range(0, self.settings.nrMinimalCells):
                self.schedule[c]['neighbor'] = self._myNeighbors()
                # log
                # self._log(
                #     INFO,
                #     "[tsch] updated minimal cell ts={0} to broadcast list {1}",
                #     (c, str(self.schedule[c]['neighbor'])),
                # )

            self._tsch_schedule_activeCell()

    def _tsch_action_synchronize(self):

        if not self.isSync:
            channel = self.genEBDIO.randint(0, self.settings.numChans - 1)
            # start listening
            self.propagation.startRx(
                mote=self,
                channel=channel,
            )
            self.onGoingReception = True
            # indicate that we're waiting for the RX operation to finish
            self.waitingFor = DIR_RX

            self._tsch_schedule_synchronize()

    def _tsch_schedule_synchronize(self):
        asn = self.engine.getAsn()

        self.engine.scheduleAtAsn(
            asn=asn + 1,
            cb=self._tsch_action_synchronize,
            uniqueTag=(self.id, '_tsch_action_synchronize'),
            priority=3,
        )

    def _tsch_add_minimal_cell(self):
        # add minimal cell
        # assert self.settings.nrMinimalCells == 3 or self.settings.nrMinimalCells == 5 or self.settings.nrMinimalCells == 7
        # self._tsch_addCells(self._myNeighbors(), [(0, 0, DIR_TXRX_SHARED)])
        # self._tsch_addCells(self._myNeighbors(), [(40, 8, DIR_TXRX_SHARED)])
        # self._tsch_addCells(self._myNeighbors(), [(80, 15, DIR_TXRX_SHARED)])
        # if self.settings.ilpfile is None:
        for c in range(0, self.settings.nrMinimalCells):
            modulation = None
            if self.settings.individualModulations == 1:
                modulation = Modulation.Modulation().minimalCellModulation[self.settings.modulationConfig]
                parentTs = c * (Modulation.Modulation().modulationSlots[self.settings.modulationConfig][modulation])
                for i in range(Modulation.Modulation().modulationSlots[self.settings.modulationConfig][modulation]):
                    self._tsch_addCells(self._myNeighbors(), [(parentTs+i, c, DIR_TXRX_SHARED)], parentTs=parentTs, modulation=modulation)
            else:
                self._tsch_addCells(self._myNeighbors(), [(c, c, DIR_TXRX_SHARED)], parentTs=c, modulation=modulation)
        # else:
        #     # assert False
        #     pass
        #     # in this case, the minimal cells are added when the ILP file is read

    # def _tsch_add_ilp_minimal_cell(self, parent_ts, channel, modulation):
    #     for i in range(Modulation.Modulation().modulationSlots[modulation]):
    #         self._tsch_addCells(self._myNeighbors(), [(parent_ts + i, channel, DIR_TXRX_SHARED)], parentTs=parent_ts, modulation=modulation)

    # ===== radio

    def _radio_drop_packet(self, pkt, reason):
        # remove all the element of pkt so that it won't be processed further
        for k in pkt.keys():
            del pkt[k]
        if reason in self.motestats:
            self._stats_incrementMoteStats(reason)

    def radio_isSync(self):
        with self.dataLock:
            return self.isSync

    def radio_txDone(self, isACKed, isNACKed):
        """end of tx slot"""

        asn = self.engine.getAsn()
        ts = asn % self.settings.slotframeLength

        with self.dataLock:

            assert ts in self.schedule
            assert self.schedule[ts]['dir'] == DIR_TX or self.schedule[ts]['dir'] == DIR_TXRX_SHARED
            assert self.waitingFor == DIR_TX

            # for debug
            ch = self.schedule[ts]['ch']
            rx = self.schedule[ts]['neighbor']
            canbeInterfered = 0
            for mote in self.engine.motes:
                if mote == self:
                    continue
                if ts in mote.schedule and ch == mote.schedule[ts]['ch'] and mote.schedule[ts]['dir'] == DIR_TX:
                    if mote.id == rx.id or mote.getRSSI(rx) > rx.minRssi:
                        canbeInterfered = 1
            self.schedule[ts]['debug_canbeInterfered'] += [canbeInterfered]

            if isACKed:
                # ACK received
                self._logChargeConsumed(CHARGE_TxDataRxAck_uC)
                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    self.nrTxDataRxAck += 1
                    self.consumption['nrTxDataRxAck'][self.schedule[ts]['modulation']] += 1
                elif not self.settings.convergeFirst:
                    self.nrTxDataRxAck += 1
                    self.consumption['nrTxDataRxAck'][self.schedule[ts]['modulation']] += 1

                # update schedule stats
                self.schedule[ts]['numTxAck'] += 1

                # update history
                self.schedule[ts]['history'] += [1]

                # update queue stats
                self._stats_logQueueDelay(asn - self.pktToSend['asn'])

                # time correction
                if self.schedule[ts]['neighbor'] == self.preferredParent:
                    self.timeCorrectedSlot = asn

                # received an ACK for the request, change state and increase the sequence number
                if self.pktToSend['type'] == IANA_6TOP_TYPE_REQUEST:
                    if self.pktToSend['code'] == IANA_6TOP_CMD_ADD:

                        assert self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] == SIX_STATE_WAIT_ADDREQUEST_SENDDONE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_WAIT_ADDRESPONSE

                        # calculate the asn at which it should fire
                        fireASN = int(self.engine.getAsn() + (
                                float(self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timeout']) / float(
                            self.settings.slotDuration)))
                        uniqueTag = '_sixtop_timer_fired_dest_%s' % self.pktToSend['dstIp'].id
                        self.engine.scheduleAtAsn(
                            asn=fireASN,
                            cb=self._sixtop_timer_fired,
                            uniqueTag=(self.id, uniqueTag),
                            priority=5,
                        )
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer'] = {}
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer']['tag'] = (self.id, uniqueTag)
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer']['asn'] = fireASN
                        self._log(
                            DEBUG,
                            "[6top] activated a timer for mote {0} to neighbor {1} on asn {2} with tag {3} ( timeout {4} )",
                            (self.id, self.pktToSend['dstIp'].id, fireASN, str((self.id, uniqueTag)), float(self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timeout'])),
                        )
                    elif self.pktToSend['code'] == IANA_6TOP_CMD_DELETE:
                        assert self.sixtopStates[self.pktToSend['dstIp'].id]['tx'][
                                   'state'] == SIX_STATE_WAIT_DELETEREQUEST_SENDDONE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_WAIT_DELETERESPONSE

                        # calculate the asn at which it should fire
                        fireASN = int(self.engine.getAsn() + (
                                    float(self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timeout']) / float(
                                self.settings.slotDuration)))
                        uniqueTag = '_sixtop_timer_fired_dest_%s' % self.pktToSend['dstIp'].id
                        self.engine.scheduleAtAsn(
                            asn=fireASN,
                            cb=self._sixtop_timer_fired,
                            uniqueTag=(self.id, uniqueTag),
                            priority=5,
                        )
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer'] = {}
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer']['tag'] = (self.id, uniqueTag)
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['timer']['asn'] = fireASN
                        self._log(
                            DEBUG,
                            "[6top] activated a timer for mote {0} to neighbor {1} on asn {2} with tag {3}",
                            (self.id, self.pktToSend['dstIp'].id, fireASN, str((self.id, uniqueTag))),
                        )
                    else:
                        assert False

                # save it in a tmp variable
                # because it is possible that self.schedule[ts] does not exist anymore after receiving an ACK for a DELETE RESPONSE
                tmpNeighbor = self.schedule[ts]['neighbor']
                tmpDir = self.schedule[ts]['dir']

                if self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:  # received an ACK for the response, handle the schedule
                    self._sixtop_receive_RESPONSE_ACK(self.pktToSend)

                if self.pktToSend[ 'type'] == APP_TYPE_DATA:  #
                    self._log(
                        DEBUG,
                        "[tsch] Successfully sent DATA packet",
                    )

                # remove packet from queue
                self.txQueue.remove(self.pktToSend)
                # reset backoff in case of shared slot or in case of a tx slot when the queue is empty
                if tmpDir == DIR_TXRX_SHARED or (tmpDir == DIR_TX and not self.txQueue):
                    if tmpDir == DIR_TXRX_SHARED and not self._isBroadcast(tmpNeighbor):
                        self._tsch_resetBackoffPerNeigh(tmpNeighbor)
                    else:
                        self._tsch_resetBroadcastBackoff()

            elif isNACKed:
                # NACK received
                self._logChargeConsumed(CHARGE_TxDataRxAck_uC)
                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    self.nrTxDataRxAck += 1
                    self.consumption['nrTxDataRxAck'][self.schedule[ts]['modulation']] += 1
                elif not self.settings.convergeFirst:
                    self.nrTxDataRxAck += 1
                    self.consumption['nrTxDataRxAck'][self.schedule[ts]['modulation']] += 1

                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    self.nrTxDataRxNack += 1
                    self.consumption['nrTxDataRxNack'][self.schedule[ts]['modulation']] += 1
                elif not self.settings.convergeFirst:
                    self.nrTxDataRxNack += 1
                    self.consumption['nrTxDataRxNack'][self.schedule[ts]['modulation']] += 1

                # update schedule stats as if it were successfully transmitted
                self.schedule[ts]['numTxAck'] += 1

                # update history
                self.schedule[ts]['history'] += [1]

                # time correction
                if self.schedule[ts]['neighbor'] == self.preferredParent:
                    self.timeCorrectedSlot = asn

                if self.pktToSend['type'] == APP_TYPE_DATA:  #
                    self._log(
                        DEBUG,
                        "[tsch] at ts {0}, UNsuccessfully sent DATA packet (NACK) --> back off {1}",
                        (ts,self.backoffPerNeigh[self.schedule[ts]['neighbor']])
                    )
                if self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:  #
                    self._log(
                        DEBUG,
                        "[tsch] at ts {0}, UNsuccessfully sent RESPONSE packet (NACK) --> back off {1}",
                        (ts,self.backoffPerNeigh[self.schedule[ts]['neighbor']])
                    )

                # decrement 'retriesLeft' counter associated with that packet
                i = self.txQueue.index(self.pktToSend)
                if self.txQueue[i]['retriesLeft'] > 0:
                    self.txQueue[i]['retriesLeft'] -= 1

                # drop packet if retried too many time
                if self.txQueue[i]['retriesLeft'] == 0:
                    # if len(self.txQueue) == TSCH_QUEUE_SIZE:

                    # only count drops of DATA packets that are part of the experiment
                    if self.pktToSend['type'] == APP_TYPE_DATA:
                        if self.settings.convergeFirst and self.pktToSend['payload'][1] >= self.engine.asnInitExperiment and self.pktToSend['payload'][1] <= self.engine.asnEndExperiment:
                            self.pktDropMac += 1
                        elif not self.settings.convergeFirst:
                            self.pktDropMac += 1
                        self._stats_incrementMoteStats('droppedDataMacRetries')

                    # update mote stats
                    self._stats_incrementMoteStats('droppedMacRetries')

                    # remove packet from queue
                    self.txQueue.remove(self.pktToSend)

                    # reset state for this neighbor
                    # go back to IDLE, i.e. remove the neighbor form the states
                    # but, in the case of a response msg, if the node received another, already new request, from the same node (because its timer fired), do not go to IDLE
                    if self.pktToSend['type'] == IANA_6TOP_TYPE_REQUEST:
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['blockedCells'] = []
                    elif self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:
                        self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['blockedCells'] = []
                    # else:
                    #     if self.pktToSend['type'] != APP_TYPE_DATA:
                    #         # update mote stats
                    #         self._stats_incrementMoteStats('droppedMacRetries')
                    # 
                    #         # remove packet from queue
                    #         self.txQueue.remove(self.pktToSend)
                    # 
                    #         if self.pktToSend['type'] == IANA_6TOP_TYPE_REQUEST:
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_IDLE
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['blockedCells'] = []
                    #         elif self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['state'] = SIX_STATE_IDLE
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['blockedCells'] = []

                # reset backoff in case of shared slot or in case of a tx slot when the queue is empty
                if self.schedule[ts]['dir'] == DIR_TXRX_SHARED or (self.schedule[ts]['dir'] == DIR_TX and not self.txQueue):
                    if self.schedule[ts]['dir'] == DIR_TXRX_SHARED and not self._isBroadcast(self.schedule[ts]['neighbor']):
                        self._tsch_resetBackoffPerNeigh(self.schedule[ts]['neighbor'])
                    else:
                        self._tsch_resetBroadcastBackoff()
            elif self.pktToSend['dstIp'] == BROADCAST_ADDRESS:
                # broadcast packet is not acked, remove from queue and update stats
                self._logChargeConsumed(CHARGE_TxData_uC)
                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    self.nrTxData += 1
                    self.consumption['nrTxData'][self.schedule[ts]['modulation']] += 1
                elif not self.settings.convergeFirst:
                    self.nrTxData += 1
                    self.consumption['nrTxData'][self.schedule[ts]['modulation']] += 1
                self.txQueue.remove(self.pktToSend)
                self._tsch_resetBroadcastBackoff()

            else:
                # neither ACK nor NACK received
                self._logChargeConsumed(CHARGE_TxDataRxAck_uC)
                if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                    self.nrTxDataNoAck += 1
                    self.consumption['nrTxDataNoAck'][self.schedule[ts]['modulation']] += 1
                elif not self.settings.convergeFirst:
                    self.nrTxDataNoAck += 1
                    self.consumption['nrTxDataNoAck'][self.schedule[ts]['modulation']] += 1

                # increment backoffExponent and get new backoff value
                if self.schedule[ts]['dir'] == DIR_TXRX_SHARED:
                    if self._isBroadcast(self.schedule[ts]['neighbor']):
                        # if self.backoffBroadcastExponent < self.settings.backoffMaxExp:
                        #     self.backoffBroadcastExponent += 1
                        if self.backoffBroadcastExponent < 4:
                            self.backoffBroadcastExponent += 1
                        self.backoffBroadcast = self.genEBDIO.randint(0, 2 ** self.backoffBroadcastExponent - 1)
                    else:
                        if self.backoffExponentPerNeigh[self.schedule[ts]['neighbor']] < self.settings.backoffMaxExp:
                            self.backoffExponentPerNeigh[self.schedule[ts]['neighbor']] += 1
                        self.backoffPerNeigh[self.schedule[ts]['neighbor']] = self.genEBDIO.randint(0, 2 **
                                                                                             self.backoffExponentPerNeigh[
                                                                                                 self.schedule[ts][
                                                                                                     'neighbor']] - 1)
                if self.pktToSend['type'] == APP_TYPE_DATA:  #
                    self._log(
                        DEBUG,
                        "[tsch] at ts {0}, UNsuccessfully sent DATA packet (NO RESPONSE), back off",
                        (ts,)
                    )
                if self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:  #
                    self._log(
                        DEBUG,
                        "[tsch] at ts {0}, UNsuccessfully sent RESPONSE packet (NO RESPONSE), back off",
                        (ts,)
                    )

                # update history
                self.schedule[ts]['history'] += [0]

                # decrement 'retriesLeft' counter associated with that packet
                i = self.txQueue.index(self.pktToSend)
                if self.txQueue[i]['retriesLeft'] > 0:
                    self.txQueue[i]['retriesLeft'] -= 1

                # drop packet if retried too many time
                if self.txQueue[i]['retriesLeft'] == 0:
                    # if len(self.txQueue) == TSCH_QUEUE_SIZE:

                    # counts drops of DATA packets
                    if self.pktToSend['type'] == APP_TYPE_DATA:
                        if self.settings.convergeFirst and self.pktToSend['payload'][1] >= self.engine.asnInitExperiment and self.pktToSend['payload'][1] <= self.engine.asnEndExperiment:
                            self.pktDropMac += 1
                        elif not self.settings.convergeFirst:
                            self.pktDropMac += 1
                        self._stats_incrementMoteStats('droppedDataMacRetries')

                    # update mote stats
                    self._stats_incrementMoteStats('droppedMacRetries')

                    # remove packet from queue
                    self.txQueue.remove(self.pktToSend)

                    # reset state for this neighbor
                    # go back to IDLE, i.e. remove the neighbor form the states
                    if self.pktToSend['type'] == IANA_6TOP_TYPE_REQUEST:
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['blockedCells'] = []
                    elif self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:
                        self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['state'] = SIX_STATE_IDLE
                        self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['blockedCells'] = []
                    # else:
                    #     if self.pktToSend['type'] != APP_TYPE_DATA:
                    #
                    #         # update mote stats
                    #         self._stats_incrementMoteStats('droppedMacRetries')
                    #
                    #         # remove packet from queue
                    #         self.txQueue.remove(self.pktToSend)
                    #
                    #         if self.pktToSend['type'] == IANA_6TOP_TYPE_REQUEST:
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['state'] = SIX_STATE_IDLE
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['tx']['blockedCells'] = []
                    #         elif self.pktToSend['type'] == IANA_6TOP_TYPE_RESPONSE:
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['state'] = SIX_STATE_IDLE
                    #             self.sixtopStates[self.pktToSend['dstIp'].id]['rx']['blockedCells'] = []

            # end of radio activity, not waiting for anything
            self.waitingFor = None

    def radio_rxDone(self, type=None, code=None, smac=None, dmac=None, srcIp=None, dstIp=None, srcRoute=None,
                     payload=None):
        """end of RX radio activity"""

        asn = self.engine.getAsn()
        ts = asn % self.settings.slotframeLength

        with self.dataLock:
            if self.isSync:
                assert ts in self.schedule
                assert self.schedule[ts]['dir'] == DIR_RX or self.schedule[ts]['dir'] == DIR_TXRX_SHARED
                assert self.waitingFor == DIR_RX

            if smac and self in dmac:  # layer 2 addressing
                # I received a packet

                if self._msf_is_enabled() and self.isSync:
                    self._msf_signal_cell_used(self.schedule[ts]['neighbor'], self.schedule[ts]['dir'], DIR_RX, type)

                if dstIp != BROADCAST_ADDRESS:  # unicast packet
                    self._logChargeConsumed(CHARGE_RxDataTxAck_uC)
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.nrRxDataTxAck += 1
                        self.consumption['nrRxDataTxAck'][self.schedule[ts]['modulation']] += 1
                    elif not self.settings.convergeFirst:
                        self.nrRxDataTxAck += 1
                        self.consumption['nrRxDataTxAck'][self.schedule[ts]['modulation']] += 1
                else:  # broadcast
                    self._logChargeConsumed(CHARGE_RxData_uC)
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.nrRxData += 1
                        self.consumption['nrRxData'][self.schedule[ts]['modulation']] += 1
                    elif not self.settings.convergeFirst:
                        self.consumption['nrRxData'][self.schedule[ts]['modulation']] += 1
                        self.nrRxData += 1

                if self.isSync:
                    # update schedule stats
                    self.schedule[ts]['numRx'] += 1

                if type == APP_TYPE_FRAG:
                    frag = {'type': type,
                            'code': code,
                            'retriesLeft': TSCH_MAXTXRETRIES,
                            'smac': smac,
                            'srcIp': srcIp,
                            'dstIp': dstIp}
                    frag['payload'] = copy.deepcopy(payload)
                    frag['sourceRoute'] = copy.deepcopy(srcRoute)
                    self.waitingFor = None
                    if (hasattr(self.settings, 'enableFragmentForwarding') and
                            self.settings.enableFragmentForwarding):
                        if self._app_is_frag_to_forward(frag) is True:
                            if self._tsch_enqueue(frag):
                                # ACK when succeeded to enqueue
                                return True, False
                            else:
                                # ACK anyway
                                self._radio_drop_packet(frag, 'droppedFragFailedEnqueue')
                                return True, False
                        elif dstIp == self:
                            if self._app_reass_packet(smac, payload) is True:
                                payload.pop()
                                type = APP_TYPE_DATA
                            else:
                                # not fully reassembled yet
                                return True, False
                        else:
                            # frag is out-of-order; ACK anyway since it's received successfully
                            return True, False
                    else:
                        if self._app_reass_packet(smac, payload) is True:
                            # remove fragment information out of payload
                            # XXX: assuming the last element has the fragment information
                            payload.pop()
                            type = APP_TYPE_DATA
                        else:
                            # ACK here
                            return True, False

                if dstIp == BROADCAST_ADDRESS:
                    if type == RPL_TYPE_DIO:
                        # got a DIO
                        # if smac.id == 0:
                        self._rpl_action_receiveDIO(type, smac, payload)

                        (isACKed, isNACKed) = (False, False)

                        self.waitingFor = None

                        return isACKed, isNACKed
                    elif type == TSCH_TYPE_EB:
                        self._tsch_action_receiveEB(type, smac, payload)

                        (isACKed, isNACKed) = (False, False)

                        self.waitingFor = None

                        return isACKed, isNACKed
                elif dstIp == self:
                    # receiving packet
                    if type == RPL_TYPE_DAO:
                        self._rpl_action_receiveDAO(type, smac, payload)
                        (isACKed, isNACKed) = (True, False)
                    elif type == IANA_6TOP_TYPE_REQUEST and code == IANA_6TOP_CMD_ADD:  # received an 6P ADD request
                        self._sixtop_receive_ADD_REQUEST(type, smac, payload)
                        (isACKed, isNACKed) = (True, False)
                    elif type == IANA_6TOP_TYPE_REQUEST and code == IANA_6TOP_CMD_DELETE:  # received an 6P DELETE request
                        self._sixtop_receive_DELETE_REQUEST(type, smac, payload)
                        (isACKed, isNACKed) = (True, False)
                    elif type == IANA_6TOP_TYPE_RESPONSE:  # received an 6P response
                        if self._sixtop_receive_RESPONSE(type, code, smac, payload):
                            (isACKed, isNACKed) = (True, False)
                        else:
                            (isACKed, isNACKed) = (False, False)
                    elif type == APP_TYPE_DATA:  # application packet
                        timestampASN = asn
                        if self.settings.individualModulations == 1:
                            timestampASN = (asn - (asn % self.settings.slotframeLength)) + self.schedule[asn % self.settings.slotframeLength]['parentTs']
                        # print 'ASN of receive = {0}, TS = {1}'.format(timestampASN, timestampASN % self.settings.slotframeLength)
                        self._app_action_receivePacket(srcIp=srcIp, payload=payload, timestamp=timestampASN)
                        (isACKed, isNACKed) = (True, False)
                    elif type == APP_TYPE_ACK:
                        self._app_action_receiveAck(srcIp=srcIp, payload=payload, timestamp=asn)
                        (isACKed, isNACKed) = (True, False)
                    elif type == APP_TYPE_JOIN:
                        self.join_receiveJoinPacket(srcIp=srcIp, payload=payload, timestamp=asn)
                        (isACKed, isNACKed) = (True, False)
                    elif type == APP_TYPE_FRAG:
                        # never comes here; but just in case
                        (isACKed, isNACKed) = (True, False)
                    else:
                        assert False
                elif type == APP_TYPE_FRAG:
                    # do nothing for fragmented packet; just ack
                    (isACKed, isNACKed) = (True, False)
                else:
                    # relaying packet

                    if type == APP_TYPE_DATA:
                        # update the number of hops
                        newPayload = copy.deepcopy(payload)
                        newPayload[2] += 1
                    else:
                        # copy the payload and forward
                        newPayload = copy.deepcopy(payload)

                    # create packet
                    relayPacket = {
                        'asn': asn,
                        'type': type,
                        'code': code,
                        'payload': newPayload,
                        'retriesLeft': TSCH_MAXTXRETRIES,
                        'srcIp': srcIp,
                        'dstIp': dstIp,
                        'sourceRoute': srcRoute,
                    }

                    # enqueue packet in TSCH queue
                    if (type == APP_TYPE_DATA and hasattr(self.settings, 'numFragments') and
                            self.settings.numFragments > 1):
                        self._app_frag_packet(relayPacket)
                        # we return ack since we've received the last fragment successfully
                        (isACKed, isNACKed) = (True, False)
                    else:
                        isEnqueued = self._tsch_enqueue(relayPacket)
                        if isEnqueued:

                            # update mote stats
                            self._stats_incrementMoteStats('appRelayed')

                            (isACKed, isNACKed) = (True, False)

                        else:
                            self._radio_drop_packet(relayPacket, 'droppedRelayFailedEnqueue')
                            (isACKed, isNACKed) = (False, True)

            else:
                # this was an idle listen

                # log charge usage
                if self.isSync:
                    self._logChargeConsumed(CHARGE_Idle_uC)
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.nrIdle += 1
                        self.consumption['nrIdle'][self.schedule[ts]['modulation']] += 1
                    elif not self.settings.convergeFirst:
                        self.nrIdle += 1
                        self.consumption['nrIdle'][self.schedule[ts]['modulation']] += 1
                else:
                    self._logChargeConsumed(CHARGE_IdleNotSync_uC)
                    if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                        self.nrIdleNotSync += 1
                        self.consumption['nrIdleNotSync'][self.schedule[ts]['modulation']] += 1
                    elif not self.settings.convergeFirst:
                        self.nrIdleNotSync += 1
                        self.consumption['nrIdleNotSync'][self.schedule[ts]['modulation']] += 1

                (isACKed, isNACKed) = (False, False)

            self.waitingFor = None

            return isACKed, isNACKed

    # ===== wireless

    def getCellPDR(self, cell):
        """ returns the pdr of the cell """

        assert cell['neighbor'] is not type(list)

        with self.dataLock:
            if cell['numTx'] < NUM_SUFFICIENT_TX:
                return self.getPDR(cell['neighbor'])
            else:
                return float(cell['numTxAck']) / float(cell['numTx'])

    def setPDR(self, neighbor, pdr):
        """ sets the pdr to that neighbor"""
        with self.dataLock:
            self.PDR[neighbor] = pdr

    def getPDR(self, neighbor):
        """ returns the pdr to that neighbor"""
        with self.dataLock:
            return self.PDR[neighbor]

    def setModulation(self, neighbor, modulation):
        """ sets the modulation to that neighbor"""
        with self.dataLock:
            self.modulation[neighbor] = modulation

    def getModulation(self, neighbor):
        """ returns the pdr to that neighbor"""
        with self.dataLock:
            if self.settings.ilpfile is not None and neighbor not in self.modulation:
                return None # in the case of the ILP, it is possible that the ILP did not allocate cells for this link, thus there is also no modulation
            elif self.settings.ilpfile is None and self.settings.genTopology == 1 and neighbor not in self.modulation:
                return None # in this case, there is something wrong
            elif self.settings.ilpfile is None and neighbor not in self.modulation:
                assert False # in this case, there is something wrong
            return self.modulation[neighbor]

    def setRSSI(self, neighbor, rssi):
        """ sets the RSSI to that neighbor"""
        with self.dataLock:
            self.RSSI[neighbor.id] = rssi

    def getRSSI(self, neighbor):
        """ returns the RSSI to that neighbor"""
        with self.dataLock:
            return self.RSSI[neighbor.id]

    def _estimateETX(self, neighbor):

        with self.dataLock:
            # set initial values for numTx and numTxAck assuming PDR is exactly estimated
            pdr = self.getPDR(neighbor)
            numTx = NUM_SUFFICIENT_TX
            numTxAck = math.floor(pdr * numTx)

            for (_, cell) in self.schedule.items():
                if (cell['neighbor'] == neighbor and cell['dir'] == DIR_TX) or (
                        cell['neighbor'] == neighbor and cell['dir'] == DIR_TXRX_SHARED):
                    numTx += cell['numTx']
                    numTxAck += cell['numTxAck']

            # abort if about to divide by 0
            if not numTxAck:
                return

            # calculate ETX
            etx = float(numTx) / float(numTxAck)

            return etx

    def _myNeighbors(self):
        return [n for n in self.PDR.keys() if self.PDR[n] > 0]

    def _isBroadcast(self, neighbor):
        if type(neighbor) is list:
            return True
        return False

    # ===== clock

    def clock_getOffsetToDagRoot(self):
        """ calculate time offset compared to the DAGroot """

        if self.dagRoot:
            return 0.0

        asn = self.engine.getAsn()
        offset = 0.0
        child = self
        parent = self.preferredParent

        while True:
            if child.timeCorrectedSlot is None:
                return 0.0
            secSinceSync = (asn - child.timeCorrectedSlot) * self.settings.slotDuration  # sec
            # FIXME: for ppm, should we not /10^6?
            relDrift = child.drift - parent.drift  # ppm
            offset += relDrift * secSinceSync  # us
            if parent.dagRoot:
                break
            else:
                child = parent
                parent = child.preferredParent

        return offset

    # ===== location

    def setLocation(self, x, y):
        with self.dataLock:
            self.x = x
            self.y = y

    def getLocation(self):
        with self.dataLock:
            return self.x, self.y

    def _calculateRepulsionVector(self, targetX, targetY, towardsCentroid=False):
        ''' Calculate the resulting repulsion vector'''

        repulsionVectorPolar = []

        startDegrees = 0
        endDegrees = 60
        scanDistance = 0.5

        # angle for the attraction
        rads = math.atan2((targetX - self.y), (targetY - self.x))
        angle = rads - (3.14159 / 2.0) + (0.017453278 * startDegrees)  # degrees
        for i in xrange(startDegrees, endDegrees, 5):  # the repulsion is checked with an array of size 12  that represent 60 degrees of search
            # from 60 degrees to 120, center at 90
            angle = angle + 0.08725  # +5 degree in rads
            # xdelta = math.cos(angle) / div
            # ydelta = math.sin(angle) / div
            xdelta = math.cos(angle) / float(1000 / 50.0)
            ydelta = math.sin(angle) / float(1000 / 50.0)
            objectx = self.x
            objecty = self.y
            distance = 0.0
            # search obstacles at every angle
            obstacleFound = False
            while not obstacleFound:
                # update distance
                distance = math.sqrt(
                    (objectx - self.x) ** 2 +
                    (objecty - self.y) ** 2
                )
                # if not obstacle, check a bit further in the same angle
                if self.engine.checkValidPosition(objectx, objecty, countSquare=False) and (distance) < scanDistance:
                    objectx = objectx + xdelta
                    objecty = objecty + ydelta
                else:
                    obstacleFound = True  # there is an obstacle at this angle and distance
                    if distance >= (scanDistance):
                        distance = scanDistance  # max is 400m
                    else:
                    #     # obstacles found before 400m, insert point
                        repulsionVectorPolar.append([angle, distance])

        # all repulsion component have been calculated
        self.repulsionVectorCart = []

        i = 0
        for (alfa, mod) in repulsionVectorPolar:
            if mod < scanDistance:  # I only save the vectors that have any obstacle
                if mod < 0.1:  # nearest objects have a surplus of repulsion
                    self.repulsionVectorCart.append([8 * (math.cos(alfa) * (scanDistance - mod)), 8 * (math.sin(alfa) * (scanDistance - mod))])
                elif mod < 0.2:  # nearest objects have a surplus of repulsion
                    self.repulsionVectorCart.append([5 * (math.cos(alfa) * (scanDistance - mod)), 5 * (math.sin(alfa) * (scanDistance - mod))])
                else:
                    self.repulsionVectorCart.append([(math.cos(alfa) * (scanDistance - mod)), (math.sin(alfa) * (scanDistance - mod))])
            i += 1

        sumRepulsionX = 0
        sumRepulsionY = 0

        # convert to cartesian to sum the components
        for (xval, yval) in self.repulsionVectorCart:
            sumRepulsionX = sumRepulsionX + xval
            sumRepulsionY = sumRepulsionY + yval
        sumRepulsionX = sumRepulsionX / float(len(self.repulsionVectorCart) + 1)  # (len(self.repulsionVectorCart)+1)
        sumRepulsionY = sumRepulsionY / float(len(self.repulsionVectorCart) + 1)  # (len(self.repulsionVectorCart)+1)

        # print 'repulsive calculation: %.20f, %.20f' % (sumRepulsionX, sumRepulsionY)

        # return the values in polar
        sumRepMod = math.sqrt(sumRepulsionX ** 2 + sumRepulsionY ** 2)
        sumRepAlfa = math.atan2(sumRepulsionY, sumRepulsionX)

        return (sumRepMod, sumRepAlfa)


    def updateLocation(self):
        ''' Update location of the mote'''

        if self.settings.mobilityModel == 'RWM':  # Random Walk Model (Brownian motion)
            speed = float(self.genMobility.gauss(self.settings.mobilitySpeed, 1)) # on average 1.5m per cycle
            div = float(1000 / speed)
            # div = 1000.0

            prevX = self.x
            prevY = self.y
            correctlyMoved = False
            while not correctlyMoved:

                rads = 2 * 3.14159 * self.genMobility.random()
                xdelta = math.cos(rads) / float(div)
                ydelta = math.sin(rads) / float(div)
                if (self.x + xdelta) < self.settings.squareSide and (self.y + ydelta) < self.settings.squareSide:
                    if self.x + xdelta > 0 and self.y + ydelta > 0:
                        correctlyMoved = True

            self.setLocation(self.x + xdelta, self.y + ydelta)

            distance = math.sqrt(
                (prevX - self.x) ** 2 +
                (prevY - self.y) ** 2
            )
            # print 'Distance of mote %d: %.8f km' % (self.id, distance)

        elif self.settings.mobilityModel == 'RPGM':  # Reference Point Group Mobility
            targetX = self.engine.targetPos[self.id][0]
            targetY = self.engine.targetPos[self.id][1]

            (repMod, repAlpha) = self._calculateRepulsionVector(targetX, targetY)

            repulsiveForce = 1
            attractiveForce = 1

            # calculated speed for the mote in this RP movement
            speed = float(self.genMobility.gauss(self.settings.mobilitySpeed, 1)) # on average 1.5m per cycle
            div = 1000 / float(speed)

            # calculate dest angle
            rads = math.atan2((targetY - self.y), (targetX - self.x))
            # print 'rads: %.20f' % (rads)

            xdelta = math.cos(rads) * attractiveForce # attraction vector
            ydelta = math.sin(rads) * attractiveForce # attraction vector
            # print 'attractive: %.20f, %.20f' % (xdelta, ydelta)

            self.attVec = (xdelta, ydelta)

            repX = -1.0 * math.cos(repAlpha) * repMod * repulsiveForce # reverse the repulsive vector
            repY = -1.0 * math.sin(repAlpha) * repMod * repulsiveForce # reverse the repulsive vector
            # print 'repulsive: %.20f, %.20f' % (repX, repY)

            self.repVec = (repX, repY)

            # resulting angle
            alfatot = math.atan2((ydelta + repY), (xdelta + repX))

            # introduce some randomness for the random comp
            randAngle = self.genMobility.randint(0, 45) * 3.14159 / 180  # random choose between 0 or 45 degrees
            r = self.genMobility.randint(-1, 1)
            while r == 0:
                r = self.genMobility.randint(-1, 1)
            randAngle *= r

            alfatot += randAngle

            xdelta_mov = math.cos(alfatot) / float(div) # x, vector result with speed
            ydelta_mov = math.sin(alfatot) / float(div) # y, vector result with speed

            self.resVec = (math.cos(alfatot), math.sin(alfatot))

            # while not correctlyMoved:	#inside the simulation square or outside the objects
            if self.engine.checkValidPosition(self.x + xdelta_mov, self.y + ydelta_mov, True):
                # set the new location based on repulsion + attraction vector
                self.setLocation(self.x + xdelta_mov, self.y + ydelta_mov)

                if (((self.x - self.engine.targetPos[self.id][0]) ** 2) + ((self.y - self.engine.targetPos[self.id][1]) ** 2)) < self.engine.goalDistanceFromTarget ** 2:
                    if self.engine.targetType[self.id] == 'up' and self.engine.targetIndex[self.id] == len(self.engine.targets)-1:
                        self.engine.targetIndex[self.id] -= 1
                        self.engine.targetType[self.id] = 'down'
                    elif self.engine.targetType[self.id] == 'down' and self.engine.targetIndex[self.id] == 0:
                        self.engine.targetIndex[self.id] += 1
                        self.engine.targetType[self.id] = 'up'
                    else:
                        if self.engine.targetType[self.id] == 'up':
                            self.engine.targetIndex[self.id] += 1
                        elif self.engine.targetType[self.id] == 'down':
                            self.engine.targetIndex[self.id] -= 1
                        else:
                            assert False

                    self.engine.targetPos[self.id] = (
                        self.engine.targets[self.engine.targetIndex[self.id]][0] + self.genMobility.uniform((-1.0 * self.engine.targetRadius) + 0.005,
                                                             self.engine.targetRadius - 0.005),
                        self.engine.targets[self.engine.targetIndex[self.id]][1] + self.genMobility.uniform((-1.0 * self.engine.targetRadius) + 0.005,
                                                             self.engine.targetRadius - 0.005))
                # RM component
                # rads = 2 * 3.14159 * random.random()  # random angle
                #
                # # constant speed of s
                # xdelta = math.sin(rads) / div
                # ydelta = math.cos(rads) / div
                #
                # # if valid location set the new location
                # if self.engine.checkValidPosition(self.x + xdelta, self.y + ydelta, True):
                #     self.setLocation(self.x + xdelta, self.y + ydelta)
                #     distance = math.sqrt(
                #         (prevx - self.x) ** 2 +
                #         (prevy - self.y) ** 2
                #     )
                # # update the distance to the destination
                # distance = math.sqrt(
                #     (targetX - self.x) ** 2 +
                #     (targetY - self.y) ** 2
                # )
                # if (1000 * distance) <= s * 2:  # if remaining meters are below the distance traveled in 1 sec(actually the speed)
                #     # destination reached. Set a new destination
                #     self.engine.targetX = 0.3
                #     self.engine.targetY = 0.1


            ##If mote is blocked
            else:
                # moving towards my parent.
                if self.id != 0:  # root mote cant be blocked
                    setNew = False
                    # while not setNew:
                    rads = math.atan2((self.preferredParent.y - self.y), (self.preferredParent.x - self.x))
                    xdelta_mov = math.cos(rads) / float(div / 5.0)  # vector result with speed constant: 10 mps
                    ydelta_mov = math.sin(rads) / float(div / 5.0)  # vector result
                    if self.engine.checkValidPosition(self.x + xdelta_mov, self.y + ydelta_mov, True):
                        # setNew = True
                        # usually should not be blocked when going toward the parent
                        self.setLocation(self.x + xdelta_mov, self.y + ydelta_mov)
                # else:
                #     setNew = False
                #     while not setNew:
                #         rads = 2 * 3.14159 * random.random()  # random angle
                #         xdelta_mov = math.cos(rads) / float(div / 5.0) # vector result with speed constant: 10 mps
                #         ydelta_mov = math.sin(rads) / float(div / 5.0) # vector result
                #         if self.engine.checkValidPosition(self.x + xdelta_mov, self.y + ydelta_mov, True):
                #             setNew = True
                #             # usually should not be blocked when going toward the parent
                #             self.setLocation(self.x + xdelta_mov, self.y + ydelta_mov)

    # ==== battery

    # def setModulation(self):
    #     self.modulation = random.choice(Modulation.modulations)
    #     self._log(INFO, "[SA] Sending at {0} kbps", (Modulation.modulationRates[self.modulation],))

    def boot(self):
        if self.settings.withJoin:
            if self.dagRoot:
                self._tsch_add_minimal_cell()
                self._init_stack()  # initialize the stack and start sending beacons and DIOs
            else:
                self._tsch_schedule_synchronize()  # permanent rx until node hears an enhanced beacon to sync
        else:
            self.isSync = True  # without join we skip the always-on listening for EBs
            self.isJoined = True  # we consider all nodes have joined
            self._tsch_add_minimal_cell()
            self._init_stack()
        for n in self._myNeighbors():
            self._log(
                INFO,
                'Modulation from mote {0} to mote {1} = {2} (RSSI = {4}, PDR = {3}, distance = {5} m)',
                (self.id, n.id, self.getModulation(n), self.getPDR(n), self.getRSSI(n), self.engine.topology._computeDistance(self, n)),
            )
        if not self.dagRoot:
            print 'My (mote %d) preferred parent is %d' % (self.id, self.preferredParent.id)

    def _init_stack(self):
        # start the stack layer by layer

        # TSCH
        if self.settings.sf != 'ilp':
            self._tsch_schedule_sendEB(firstEB=True)

        # RPL
        if self.settings.ilpfile is None:
            self._rpl_schedule_sendDIO(firstDIO=True)
        if not self.dagRoot:
            if self.settings.ilpfile is None:
                self._rpl_schedule_sendDAO(firstDAO=True)

        # if not join, set the neighbor variables when initializing stack. With join this is done when the nodes become synced. If root, initialize here anyway
        if not self.settings.withJoin or self.dagRoot:
            # for m in self._myNeighbors():
            #     self._tsch_resetBackoffPerNeigh(m)
            for m in self.engine.motes:
                if m.id != self.id:
                    self._tsch_resetBackoffPerNeigh(m)

        # MSF
        if self._msf_is_enabled():
            self._msf_schedule_housekeeping()

        # app
        # if not self.dagRoot:
        #     if hasattr(self.settings, 'numPacketsBurst') and self.settings.numPacketsBurst != None and self.settings.burstTimestamp != None:
        #         self._app_schedule_sendPacketBurst()
        #     else:
        #         self._app_schedule_sendSinglePacket(firstPacket=True)

    def _logChargeConsumed(self, charge):
        with self.dataLock:
            if self.settings.convergeFirst and self.engine.asn >= self.engine.asnInitExperiment and self.engine.asn <= self.engine.asnEndExperiment:
                self.chargeConsumed += charge

    def set_distance(self, mote, distance):
        self.distanceTo[mote] = distance
    
    def get_distance(self, mote):
        if mote in self.distanceTo:
            return self.distanceTo[mote]
        return None

    # ======================== private =========================================

    # ===== getters

    def getTxCells(self, neighbor=None):
        with self.dataLock:
            if neighbor is None:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_TX]
            else:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_TX and c['neighbor'] == neighbor]

    def getRxCells(self, neighbor=None):
        with self.dataLock:
            if neighbor is None:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_RX]
            else:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_RX and c['neighbor'] == neighbor]

    def getSharedCells(self, neighbor=None):
        with self.dataLock:
            if neighbor is None:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_TXRX_SHARED]
            else:
                return [(ts, c['ch'], c['neighbor']) for (ts, c) in self.schedule.items() if c['dir'] == DIR_TXRX_SHARED and c['neighbor'] == neighbor]

    # ===== stats

    # mote state

    def getMoteStats(self):

        # gather statistics
        with self.dataLock:
            dataPktQueues = 0
            for p in self.txQueue:
                if not self.settings.convergeFirst and p['type'] == APP_TYPE_DATA:
                    dataPktQueues += 1
                elif self.settings.convergeFirst and p['type'] == APP_TYPE_DATA and p['payload'][1] >= self.engine.asnInitExperiment and p['payload'][1] <= self.engine.asnEndExperiment:
                    dataPktQueues += 1

            returnVal = copy.deepcopy(self.motestats)
            returnVal['numTxCells'] = len(self.getTxCells())
            returnVal['numRxCells'] = len(self.getRxCells())
            returnVal['numDedicatedCells'] = len([(ts, c) for (ts, c) in self.schedule.items() if type(self) == type(c['neighbor'])])
            returnVal['numSharedCells'] = len(self.getSharedCells())
            returnVal['aveQueueDelay'] = self._stats_getAveQueueDelay()
            returnVal['aveLatency'] = self._stats_getAveLatency()
            returnVal['aveHops'] = self._stats_getAveHops()
            returnVal['probableCollisions'] = self._stats_getRadioStats('probableCollisions')
            returnVal['txQueueFill'] = len(self.txQueue)
            returnVal['chargeConsumed'] = self.chargeConsumed
            returnVal['numTx'] = sum([cell['numTx'] for (_, cell) in self.schedule.items()])
            returnVal['pktReceived'] = self.pktReceived
            returnVal['pktGen'] = self.pktGen
            returnVal['pktDropQueue'] = self.pktDropQueue
            returnVal['pktDropMac'] = self.pktDropMac
            returnVal['arrivedToGen'] = self.arrivedToGen
            returnVal['notGenerated'] = self.notGenerated
            returnVal['dataQueueFill'] = dataPktQueues
            returnVal['aveSixtopLatency'] = self._stats_getAveSixTopLatency()

        # reset the statistics
        self._stats_resetMoteStats()
        self._stats_resetQueueStats()
        self._stats_resetLatencyStats()
        self._stats_resetHopsStats()
        self._stats_resetRadioStats()
        self._stats_resetSixTopLatencyStats()

        return returnVal

    def _stats_resetMoteStats(self):
        with self.dataLock:
            self.motestats = {
                # app
                'appGenerated': 0,  # number of packets app layer generated
                'appRelayed': 0,  # number of packets relayed
                'appReachesDagroot': 0,  # number of packets received at the DAGroot
                'droppedFailedEnqueue': 0,  # dropped packets because failed enqueue them
                'droppedDataFailedEnqueue': 0,  # dropped DATA packets because app failed enqueue them
                # queue
                'droppedQueueFull': 0,  # dropped packets because queue is full
                # rpl
                'rplTxDIO': 0,  # number of TX'ed DIOs
                'rplRxDIO': 0,  # number of RX'ed DIOs
                'rplTxDAO': 0,  # number of TX'ed DAOs
                'rplRxDAO': 0,  # number of RX'ed DAOs
                'rplChurnPrefParent': 0,  # number of time the mote changes preferred parent
                'rplChurnRank': 0,  # number of time the mote changes rank
                'rplChurnParentSet': 0,  # number of time the mote changes parent set
                'droppedNoRoute': 0,  # packets dropped because no route (no preferred parent)
                'droppedNoTxCells': 0,  # packets dropped because no TX cells
                # 6top
                '6topTxRelocatedCells': 0,  # number of time tx-triggered 6top relocates a single cell
                '6topTxRelocatedBundles': 0,  # number of time tx-triggered 6top relocates a bundle
                '6topRxRelocatedCells': 0,  # number of time rx-triggered 6top relocates a single cell
                '6topTxAddReq': 0,  # number of 6P Add request transmitted
                '6topTxAddResp': 0,  # number of 6P Add responses transmitted
                '6topTxDelReq': 0,  # number of 6P del request transmitted
                '6topTxDelResp': 0,  # number of 6P del responses transmitted
                '6topRxAddReq': 0,  # number of 6P Add request received
                '6topRxAddResp': 0,  # number of 6P Add responses received
                '6topRxDelReq': 0,  # number of 6P Del request received
                '6topRxDelResp': 0,  # number of 6P Del responses received
                # tsch
                'droppedMacRetries': 0,  # packets dropped because more than TSCH_MAXTXRETRIES MAC retries
                'droppedDataMacRetries': 0,
            # packets dropped because more than TSCH_MAXTXRETRIES MAC retries in a DATA packet
                'tschTxEB': 0,  # number of TX'ed EBs
                'tschRxEB': 0,  # number of RX'ed EBs
            }

    def _stats_incrementMoteStats(self, name):
        with self.dataLock:
            self.motestats[name] += 1

    # cell stats

    def getCellStats(self, ts_p, ch_p):
        """ retrieves cell stats """

        returnVal = None
        with self.dataLock:
            for (ts, cell) in self.schedule.items():
                if ts == ts_p and cell['ch'] == ch_p:
                    returnVal = {
                        'dir': cell['dir'],
                        'neighbor': [node.id for node in cell['neighbor']] if type(cell['neighbor']) is list else cell[
                            'neighbor'].id,
                        'numTx': cell['numTx'],
                        'numTxAck': cell['numTxAck'],
                        'numRx': cell['numRx'],
                    }
                    break
        return returnVal

    def stats_sharedCellCollisionSignal(self):
        asn = self.engine.getAsn()
        ts = asn % self.settings.slotframeLength

        assert self.schedule[ts]['dir'] == DIR_TXRX_SHARED

        with self.dataLock:
            self.schedule[ts]['sharedCellCollision'] = 1

    def stats_sharedCellSuccessSignal(self):
        asn = self.engine.getAsn()
        ts = asn % self.settings.slotframeLength

        assert self.schedule[ts]['dir'] == DIR_TXRX_SHARED

        with self.dataLock:
            self.schedule[ts]['sharedCellSuccess'] = 1

    def getSharedCellStats(self):
        returnVal = {}
        # gather statistics
        with self.dataLock:
            for (ts, cell) in self.schedule.items():
                if cell['dir'] == DIR_TXRX_SHARED:
                    returnVal['sharedCellCollision_{0}_{1}'.format(ts, cell['ch'])] = cell['sharedCellCollision']
                    returnVal['sharedCellSuccess_{0}_{1}'.format(ts, cell['ch'])] = cell['sharedCellSuccess']

                    # reset the statistics
                    cell['sharedCellCollision'] = 0
                    cell['sharedCellSuccess'] = 0

        return returnVal

    # queue stats

    def _stats_logQueueDelay(self, delay):
        with self.dataLock:
            self.queuestats['delay'] += [delay]

    def _stats_getAveQueueDelay(self):
        d = self.queuestats['delay']
        return float(sum(d)) / len(d) if len(d) > 0 else 0

    def _stats_resetQueueStats(self):
        with self.dataLock:
            self.queuestats = {
                'delay': [],
            }

    # latency stats

    def _stats_logLatencyStat(self, latency):
        with self.dataLock:
            self.packetLatencies += [latency]

    def _stats_logSixTopLatencyStat(self, latency):
        with self.dataLock:
            self.avgsixtopLatency += [latency]

    def _stats_getAveLatency(self):
        with self.dataLock:
            d = self.packetLatencies
            return float(sum(d)) / float(len(d)) if len(d) > 0 else 0

    def _stats_getAveSixTopLatency(self):
        with self.dataLock:
            d = self.avgsixtopLatency
            return float(sum(d)) / float(len(d)) if len(d) > 0 else 0

    def _stats_resetLatencyStats(self):
        with self.dataLock:
            self.packetLatencies = []

    def _stats_resetSixTopLatencyStats(self):
        with self.dataLock:
            self.avgsixtopLatency = []

    # hops stats

    def _stats_logHopsStat(self, hops):
        with self.dataLock:
            self.packetHops += [hops]

    def _stats_getAveHops(self):
        with self.dataLock:
            d = self.packetHops
            return float(sum(d)) / float(len(d)) if len(d) > 0 else 0

    def _stats_resetHopsStats(self):
        with self.dataLock:
            self.packetHops = []

    # radio stats

    def stats_incrementRadioStats(self, name):
        with self.dataLock:
            self.radiostats[name] += 1

    def _stats_getRadioStats(self, name):
        return self.radiostats[name]

    def _stats_resetRadioStats(self):
        with self.dataLock:
            self.radiostats = {
                'probableCollisions': 0,  # number of packets that can collide with another packets
            }

    # ===== log

    def _log(self, severity, template, params=()):

        if severity == DEBUG:
            if not log.isEnabledFor(logging.DEBUG):
                return
            logfunc = log.debug
        elif severity == INFO:
            if not log.isEnabledFor(logging.INFO):
                return
            logfunc = log.info
        elif severity == WARNING:
            if not log.isEnabledFor(logging.WARNING):
                return
            logfunc = log.warning
        elif severity == ERROR:
            if not log.isEnabledFor(logging.ERROR):
                return
            logfunc = log.error
        else:
            raise NotImplementedError()

        output = []
        output += ['[ASN={0:>6} id={1:>4}] '.format(self.engine.getAsn(), self.id)]
        output += [template.format(*params)]
        output = ''.join(output)
        logfunc(output)
