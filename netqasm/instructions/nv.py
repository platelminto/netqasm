from dataclasses import dataclass
import numpy as np

import netqasm.instructions.core as core
from netqasm.quantum_gates import get_rotation_matrix


# Explicit instruction types in the NV flavour.

@dataclass
class GateXInstruction(core.SingleQubitInstruction):
    id: int = 20
    mnemonic: str = "x"

    def to_matrix(self) -> np.array:
        return np.array([
            [0, 1],
            [1, 0]])


@dataclass
class GateYInstruction(core.SingleQubitInstruction):
    id: int = 21
    mnemonic: str = "y"

    def to_matrix(self) -> np.array:
        return np.array([
            [0, -1j],
            [1j, 0]])


@dataclass
class GateZInstruction(core.SingleQubitInstruction):
    id: int = 22
    mnemonic: str = "z"

    def to_matrix(self) -> np.array:
        return np.array([
            [1, 0],
            [0, -1]])


@dataclass
class GateHInstruction(core.SingleQubitInstruction):
    id: int = 23
    mnemonic: str = "h"

    def to_matrix(self) -> np.array:
        X = GateXInstruction().to_matrix()
        Z = GateZInstruction().to_matrix()
        return (X + Z) / np.sqrt(2)


@dataclass
class RotXInstruction(core.RotationInstruction):
    id: int = 27
    mnemonic: str = "rot_x"

    def to_matrix(self) -> np.array:
        axis = [1, 0, 0]
        angle = self.angle_num.value * np.pi / 2 ** self.angle_denom.value
        return get_rotation_matrix(axis, angle)


@dataclass
class RotYInstruction(core.RotationInstruction):
    id: int = 28
    mnemonic: str = "rot_y"

    def to_matrix(self) -> np.array:
        axis = [0, 1, 0]
        angle = self.angle_num.value * np.pi / 2 ** self.angle_denom.value
        return get_rotation_matrix(axis, angle)


@dataclass
class RotZInstruction(core.RotationInstruction):
    id: int = 29
    mnemonic: str = "rot_z"

    def to_matrix(self) -> np.array:
        axis = [0, 0, 1]
        angle = self.angle_num.value * np.pi / 2 ** self.angle_denom.value
        return get_rotation_matrix(axis, angle)


@dataclass
class CnotInstruction(core.TwoQubitInstruction):
    id: int = 30
    mnemonic: str = "cnot"

    def to_matrix(self) -> np.array:
        return np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 1, 0]])

    def to_matrix_target_only(self) -> np.array:
        return np.array([
            [0, 1],
            [1, 0]
        ])


@dataclass
class CSqrtXInstruction(core.TwoQubitInstruction):
    id: int = 31
    mnemonic: str = "csqx"

    def to_matrix(self) -> np.array:
        return np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1 * np.sqrt(1j/2), -1j * np.sqrt(1j/2)],
            [0, 0, -1j * np.sqrt(1j/2), 1 * np.sqrt(1j/2)]])

    def to_matrix_target_only(self) -> np.array:
        return np.array([
            [1, -1j],
            [-1j, 1]
        ]) * np.sqrt(1j/2)