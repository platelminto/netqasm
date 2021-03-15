from __future__ import annotations
from typing import TYPE_CHECKING
from typing import Tuple, Union, List, Optional, Callable

import logging

"""TODO write about epr sockets"""

import abc
from contextlib import contextmanager
from enum import Enum, auto

from qlink_interface import (
    EPRType,
    LinkLayerOKTypeK,
    LinkLayerOKTypeM,
    LinkLayerOKTypeR,
    RandomBasis,
)

from netqasm.logging.glob import get_netqasm_logger
from netqasm.lang.instr.instr_enum import Instruction

from netqasm.sdk import Qubit

if TYPE_CHECKING:
    from netqasm.sdk.connection import BaseNetQASMConnection

T_LinkLayerOkList = Union[
    List[LinkLayerOKTypeK], List[LinkLayerOKTypeM], List[LinkLayerOKTypeR]
]


class EPRMeasBasis(Enum):
    X = 0
    Y = auto()
    Z = auto()


class NoCircuitError(RuntimeError):
    pass


def _assert_has_conn(method):
    def new_method(self, *args, **kwargs):
        if self._conn is None:
            raise NoCircuitError(
                "To use the socket it first needs to be setup by giving it to a `NetQASMConnection`"
            )
        return method(self, *args, **kwargs)

    new_method.__doc__ = method.__doc__
    return new_method


class EPRSocket(abc.ABC):
    def __init__(
        self,
        remote_app_name: str,
        epr_socket_id: int = 0,
        remote_epr_socket_id: int = 0,
        min_fidelity: int = 100,
    ):
        """Encapsulates the notion of an EPR socket which sets up a virtual circuit in the network
        when instantiated and can then be used for entanglement generation.

        Parameters
        ----------
        remote_node_name : str
            Name of the remote node to entangle with.
        epr_socket_id : int
            The identifier used for this socket.
        remote_epr_socket_id : int
            The identifier used by the remote node.
        min_fidelity : int
            The minimum desired fidelity of EPR pairs generated using this socket.
            Values are integers in the range 0-100.
        """
        self._conn: Optional[BaseNetQASMConnection] = None
        self._remote_app_name: str = remote_app_name
        self._remote_node_id: Optional[
            int
        ] = None  # Gets set when the connection is set
        self._epr_socket_id: int = epr_socket_id
        self._remote_epr_socket_id: int = remote_epr_socket_id

        if (
            not isinstance(min_fidelity, int)
            or (min_fidelity < 0)
            or min_fidelity > 100
        ):
            raise ValueError(
                f"min_fidelity must be an integer in the range [0, 100], not {min_fidelity}"
            )
        self._min_fidelity: int = min_fidelity

        self._logger: logging.Logger = get_netqasm_logger(
            f"{self.__class__.__name__}({self._remote_app_name}, {self._epr_socket_id})"
        )

    @property
    def conn(self) -> BaseNetQASMConnection:
        """Get the underlying :class:`NetQASMConnection`"""
        if self._conn is None:
            raise RuntimeError("EPRSocket does not have an open connection")
        return self._conn

    @conn.setter
    def conn(self, conn: BaseNetQASMConnection):
        self._conn = conn
        self._remote_node_id = self._get_node_id(app_name=self._remote_app_name)

    @property
    def remote_app_name(self) -> str:
        """Get the remote application name"""
        return self._remote_app_name

    @property
    def remote_node_id(self) -> int:
        """Get the remote node ID"""
        if self._remote_node_id is None:
            raise RuntimeError("Remote Node ID has not been initialized")
        return self._remote_node_id

    @property
    def epr_socket_id(self) -> int:
        """Get the EPR socket ID"""
        return self._epr_socket_id

    @property
    def remote_epr_socket_id(self) -> int:
        """Get the remote EPR socket ID"""
        return self._remote_epr_socket_id

    @property
    def min_fidelity(self) -> int:
        """Get the desired minimum fidelity"""
        return self._min_fidelity

    # TODO: remove commented-out decorators
    # @_assert_has_conn
    def create(
        self,
        number: int = 1,
        post_routine: Optional[Callable] = None,
        sequential: bool = False,
        tp: EPRType = EPRType.K,
        basis_local: EPRMeasBasis = None,
        basis_remote: EPRMeasBasis = None,
        rotations_local: Tuple[int, int, int] = (0, 0, 0),
        rotations_remote: Tuple[int, int, int] = (0, 0, 0),
        random_basis_local: Optional[RandomBasis] = None,
        random_basis_remote: Optional[RandomBasis] = None,
    ) -> Union[
        List[Qubit],
        List[LinkLayerOKTypeK],
        List[LinkLayerOKTypeM],
        List[LinkLayerOKTypeR],
    ]:
        # First line is to have the correct signature after decorating
        """
        create(self, number=1, post_routine=None, sequential=False, tp=EPRType.K, \
        random_basis_local=None, random_basis_remote=None)
        Creates EPR pair with a remote node

        Parameters
        ----------
        number : int
            The number of pairs to create
        post_routine : function
            Can be used to specify what should happen when entanglement is generated
            for each pair.
            The function should take three arguments `(conn, q, pair)` where
            * `conn` is the connection (e.g. `self`)
            * `q` is the entangled qubit (of type :class:`netqasm.qubit._FutureQubit`)
            * `pair` is a loop register stating which pair is handled (0, 1, ...)

            for example to state that the qubit should be measured in the Hadamard basis
            one can provide the following function

            .. code-block::

                def post_create(conn, q, pair):
                    q.H()
                    q.measure(future=outcomes.get_future_index(pair))

            where `outcomes` is an already allocated array and `pair` is then used to
            put the outcome at the correct index of the array.

            NOTE: If the a qubit is measured (not inplace) in a `post_routine` but is
            also used by acting on the returned objects of `createEPR` this cannot
            be checked in compile-time and will raise an error during the execution
            of the full subroutine in the backend.
        sequential : bool, optional
            If this is specified to `True` each qubit will have the same virtual address
            and there will maximally be one pair in memory at a given time.
            If `number` is greater than 1 a post_routine should be specified which
            consumed each pair.

            NOTE: If `sequential` is `False` (default), `number` cannot be greater than
                  the size of the unit module. However, if `sequential` is `True` is can.
        tp : :class:`~.EPRType`
            What type of request, i.e. either `K` (create and keep),
            `M` (measure-directly) or `R` (remote state preparation).
            Depending on the type of request the method will return different things,
            for example if the request is of type `K` a list of qubits will be returned:

            .. code-block::

                qubits = epr_socket.create(number=3, tp=EPRType.K)
                for q in qubits:
                    q.H()

            however for type `M` requests it will be a list of entanglement generations:

            .. code-block::

                ent_infos = epr_socket.create(number=3, tp=EPRType.K)
                for ent_info in ent_infos:
                    assert isinstance(ent_info, tuple)
        """
        if basis_local == EPRMeasBasis.X:
            rotations_local = (0, 24, 0)
        elif basis_local == EPRMeasBasis.Y:
            rotations_local = (8, 0, 0)
        elif basis_local == EPRMeasBasis.Z:
            rotations_local = (0, 0, 0)
        elif basis_local is None:
            pass  # use rotations_local argument value
        else:
            raise ValueError(f"Unsupported EPR measurement basis: {basis_local}")

        if basis_remote == EPRMeasBasis.X:
            rotations_remote = (0, 24, 0)
        elif basis_remote == EPRMeasBasis.Y:
            rotations_remote = (8, 0, 0)
        elif basis_remote == EPRMeasBasis.Z:
            rotations_remote = (0, 0, 0)
        elif basis_remote is None:
            pass  # use rotations_remote argument value
        else:
            raise ValueError(f"Unsupported EPR measurement basis: {basis_remote}")

        return self.conn.create_epr(  # type: ignore
            remote_node_id=self.remote_node_id,
            epr_socket_id=self._epr_socket_id,
            number=number,
            post_routine=post_routine,
            sequential=sequential,
            tp=tp,
            random_basis_local=random_basis_local,
            random_basis_remote=random_basis_remote,
            rotations_local=rotations_local,
            rotations_remote=rotations_remote,
        )

    @contextmanager
    # @_assert_has_conn
    def create_context(self, number: int = 1, sequential: bool = False):
        """Creates EPR pairs with a remote node and handles each pair by
        the operations defined in a subsequent context, see example below.

        Example
        -------
        To create two pairs and measure both of these in the Hadamard basis one can do as follows:

        .. code-block::

            with epr_socket.create_context(number=num) as (q, pair):
                q.H()
                m = q.measure()

        NOTE: The `sequential` flag can be used to specify if the qubits should use the same
        virtual qubit and there only exists one at a time or not.


        Parameters
        ----------
        number : int
            The number of pairs to create
        post_routine : function
            Can be used to specify what should happen when entanglement is generated
            for each pair.
            The function should take three arguments `(conn, q, pair)` where
            * `conn` is the connection (e.g. `self`)
            * `q` is the entangled qubit (of type :class:`netqasm.qubit._FutureQubit`)
            * `pair` is a loop register stating which pair is handled (0, 1, ...)

            for example to state that the qubit should be measured in the Hadamard basis
            one can provide the following function

            .. code-block::

                def post_create(conn, q, pair):
                    q.H()
                    q.measure(future=outcomes.get_future_index(pair))

            where `outcomes` is an already allocated array and `pair` is then used to
            put the outcome at the correct index of the array.

            NOTE: If the a qubit is measured (not inplace) in a `post_routine` but is
            also used by acting on the returned objects of `createEPR` this cannot
            be checked in compile-time and will raise an error during the execution
            of the full subroutine in the backend.
        sequential : bool, optional
            If this is specified to `True` each qubit will have the same virtual address
            and there will maximally be one pair in memory at a given time.
            If `number` is greater than 1 a post_routine should be specified which
            consumed each pair.

            NOTE: If `sequential` is `False` (default), `number` cannot be greater than
                  the size of the unit module. However, if `sequential` is `True` is can.
        """
        try:
            instruction = Instruction.CREATE_EPR
            # NOTE loop_register is the register used for looping over the generated pairs
            (
                pre_commands,
                loop_register,
                ent_info_array,
                output,
                pair,
            ) = self.conn._pre_epr_context(
                instruction=instruction,
                remote_node_id=self.remote_node_id,
                epr_socket_id=self._epr_socket_id,
                number=number,
                sequential=sequential,
                tp=EPRType.K,
            )
            yield output, pair
        finally:
            self.conn._post_epr_context(
                pre_commands=pre_commands,
                number=number,
                loop_register=loop_register,
                ent_info_array=ent_info_array,
                pair=pair,
            )

    # @_assert_has_conn
    def recv(
        self,
        number: int = 1,
        post_routine: Optional[Callable] = None,
        sequential: bool = False,
        tp: EPRType = EPRType.K,
    ) -> Union[List[Qubit], T_LinkLayerOkList]:
        # First line is to have the correct signature after decorating
        """
        recv(self, number=1, post_routine=None, sequential=False, tp=EPRType.K)
        Receives EPR pair with a remote node (see doc of :meth:`~.create`)
        """

        if self.conn is None:
            raise RuntimeError("EPRSocket does not have an open connection")

        return self.conn.recv_epr(
            remote_node_id=self.remote_node_id,
            epr_socket_id=self._epr_socket_id,
            number=number,
            post_routine=post_routine,
            sequential=sequential,
            tp=tp,
        )

    @contextmanager
    # @_assert_has_conn
    def recv_context(self, number: int = 1, sequential: bool = False):
        """Receives EPR pair with a remote node (see doc of :meth:`~.create_context`)"""
        try:
            instruction = Instruction.RECV_EPR
            # NOTE loop_register is the register used for looping over the generated pairs
            (
                pre_commands,
                loop_register,
                ent_info_array,
                output,
                pair,
            ) = self.conn._pre_epr_context(
                instruction=instruction,
                remote_node_id=self.remote_node_id,
                epr_socket_id=self._epr_socket_id,
                number=number,
                sequential=sequential,
                tp=EPRType.K,
            )
            yield output, pair
        finally:
            self.conn._post_epr_context(
                pre_commands=pre_commands,
                number=number,
                loop_register=loop_register,
                ent_info_array=ent_info_array,
                pair=pair,
            )

    # @_assert_has_conn
    def _get_node_id(self, app_name: str) -> int:
        return self.conn.network_info.get_node_id_for_app(app_name=app_name)
