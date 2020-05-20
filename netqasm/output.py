import abc
from enum import Enum
from datetime import datetime

from netqasm.instructions import (
    Instruction,
    instruction_to_string,
    QUBIT_GATES,
    SINGLE_QUBIT_GATES,
    EPR_INSTR,
)
from netqasm.subroutine import Register, ArrayEntry
from netqasm.yaml_util import dump_yaml


INSTR_TO_LOG = QUBIT_GATES + EPR_INSTR + [Instruction.MEAS]


class InstrField(Enum):
    WCT = "WCT"  # Wall clock time
    SIT = "SIT"  # Simulated time
    SID = "SID"  # Subroutine ID
    PRC = "PRC"  # Program counter
    HLN = "HLN"  # Host line number
    INS = "INS"  # Instruction
    OPR = "OPR"  # Operands (register, array-entries..)
    OPV = "OPV"  # Values of operands as stored in memory
    OUT = "OUT"  # Measurement outcome
    QST = "QST"  # Single-qubit state after operation
    LOG = "LOG"  # Human-readable message


class StructuredLogger(abc.ABC):
    def __init__(self, filepath):
        self._filepath = filepath

        self._storage = []

    def log(self, **kwargs):
        entry = self._construct_entry(**kwargs)
        if entry is not None:
            self._storage.append(entry)

    @abc.abstractmethod
    def _construct_entry(self, **kwargs):
        pass

    def _get_current_qubit_state(self, subroutine_id, qubit_address_reg):
        app_id = self._executioner._get_app_id(subroutine_id=subroutine_id)
        virtual_address = self._executioner._get_register(app_id=app_id, register=qubit_address_reg)
        state = self._executioner._get_qubit_state(app_id=app_id, virtual_address=virtual_address)
        return state.tolist()

    def _get_op_values(self, subroutine_id, operands):
        values = []
        app_id = self._executioner._get_app_id(subroutine_id=subroutine_id)
        for operand in operands:
            value = None
            if isinstance(operand, int):
                value = operand
            elif isinstance(operand, Register):
                value = self._executioner._get_register(app_id=app_id, register=operand)
            elif isinstance(operand, ArrayEntry):
                value = self._executioner._get_array_entry(app_id=app_id, array_entry=operand)
            values.append(value)
        return values

    def save(self):
        dump_yaml(self._storage, self._filepath)

    def __del__(self):
        self.save()


class InstrLogger(StructuredLogger):
    def __init__(self, filepath, executioner):
        super().__init__(filepath)
        self._executioner = executioner

    def _construct_entry(self, **kwargs):
        command = kwargs['command']
        if command.instruction not in INSTR_TO_LOG:
            return None
        subroutine_id = kwargs['subroutine_id']
        output = kwargs['output']
        wall_time = str(datetime.now())
        sim_time = self._executioner._get_simulated_time()
        program_counter = self._executioner._program_counters[subroutine_id]
        instr_name = instruction_to_string(command.instruction)
        operands = command.operands
        ops_str = [str(op) for op in operands]
        op_values = self._get_op_values(subroutine_id=subroutine_id, operands=operands)
        log = f"Doing instruction {instr_name} with operands {ops_str}"
        if command.instruction in SINGLE_QUBIT_GATES + [Instruction.MEAS]:
            qubit_address_reg = operands[0]
            qubit_state = self._get_current_qubit_state(
                subroutine_id=subroutine_id,
                qubit_address_reg=qubit_address_reg,
            )
        else:
            qubit_state = None
        if command.instruction == Instruction.MEAS:
            outcome = output
        else:
            outcome = None
        return {
            InstrField.WCT.value: wall_time,
            InstrField.SIT.value: sim_time,
            InstrField.SID.value: subroutine_id,
            InstrField.PRC.value: program_counter,
            InstrField.HLN.value: None,
            InstrField.INS.value: instr_name,
            InstrField.OPR.value: ops_str,
            InstrField.OPV.value: op_values,
            InstrField.OUT.value: outcome,
            InstrField.QST.value: qubit_state,
            InstrField.LOG.value: log,
        }


class SocketOperation(Enum):
    SEND = "SEND"
    RECV = "RECV"
    WAIT_RECV = "WAIT_RECV"


class ClassCommField(Enum):
    WCT = InstrField.WCT.value  # Wall clock time
    HLN = InstrField.HLN.value  # Simulated time
    INS = InstrField.INS.value  # Instruction (SEND, WAIT_RECV or RECV)
    MSG = "MSG"  # Message sent or received
    SEN = "SEN"  # Sender
    REC = "REC"  # Receiver
    SOD = "SOD"  # Socket ID
    LOG = InstrField.LOG.value  # Human-readable message


class ClassCommLogger(StructuredLogger):
    def _construct_entry(self, **kwargs):
        socket_op = kwargs['socket_op']
        msg = kwargs['msg']
        sender = kwargs['sender']
        receiver = kwargs['receiver']
        socket_id = kwargs['socket_id']
        hln = kwargs['hln']
        log = kwargs['log']
        wall_time = str(datetime.now())
        return {
            ClassCommField.WCT.value: wall_time,
            ClassCommField.HLN.value: hln,
            ClassCommField.INS.value: socket_op.value,
            ClassCommField.MSG.value: msg,
            ClassCommField.SEN.value: sender,
            ClassCommField.REC.value: receiver,
            ClassCommField.SOD.value: socket_id,
            ClassCommField.LOG.value: log,
        }