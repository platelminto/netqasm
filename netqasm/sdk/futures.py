import abc

from netqasm.parsing import parse_register, parse_address
from netqasm.subroutine import Constant, Symbols, Command, Register
from netqasm.instructions import Instruction


class NoValueError(RuntimeError):
    pass


class NonConstantIndexError(RuntimeError):
    pass


def as_int_when_value(cls):
    """A decorator for the class `Future` which makes is behave like an `int`
    when the property `value` is not `None`.
    """
    def wrap_method(method_name):
        """Returns a new method for the class given a method name"""
        int_method = getattr(int, method_name)

        def new_method(self, *args, **kwargs):
            """Checks if the value is set, other raises an error"""
            value = self.value
            if value is None:
                raise NoValueError(f"The object '{repr(self)}' has no value yet, "
                                   "consider flusing the current subroutine")
            return int_method(value, *args, **kwargs)

        return new_method

    method_names = [
        "__abs__",
        "__add__",
        "__and__",
        "__bool__",
        "__ceil__",
        "__divmod__",
        "__eq__",
        "__float__",
        "__floor__",
        "__floordiv__",
        "__ge__",
        "__gt__",
        "__hash__",
        "__int__",
        "__invert__",
        "__le__",
        "__lshift__",
        "__lt__",
        "__mod__",
        "__mul__",
        "__ne__",
        "__neg__",
        "__or__",
        "__pos__",
        "__pow__",
        "__radd__",
        "__rand__",
        "__rdivmod__",
        "__rfloordiv__",
        "__rlshift__",
        "__rmod__",
        "__rmul__",
        "__ror__",
        "__round__",
        "__rpow__",
        "__rrshift__",
        "__rshift__",
        "__rsub__",
        "__rtruediv__",
        "__rxor__",
        "__sub__",
        "__truediv__",
        "__xor__",
        "bit_length",
        "conjugate",
        "denominator",
        "imag",
        "numerator",
        "real",
        "to_bytes",
    ]
    for method_name in method_names:
        setattr(cls, method_name, wrap_method(method_name))
    return cls


@as_int_when_value
class Future(int):
    @classmethod
    def __new__(cls, *args, **kwargs):
        return int.__new__(cls, 0)

    def __init__(self, connection, address, index):
        self._value = None
        self._connection = connection
        self._address = address
        self._index = index

    def __str__(self):
        value = self.value
        if value is None:
            return (f"{self.__class__.__name__} to be stored in array with address "
                    f"{self._address} at index {self._index}.\n"
                    "To access the value, the subroutine must first be executed which can be done by flushing.")
        else:
            return str(value)

    def __repr__(self):
        return f"{self.__class__} with value={self.value}"

    @property
    def value(self):
        if self._value is not None:
            return self._value
        if not isinstance(self._index, int):
            raise NonConstantIndexError("index is not constant and cannot be resolved")
        value = self._connection._shared_memory.get_array_part(address=self._address, index=self._index)
        if value is not None:
            self._value = value
        return value

    def add(self, other, mod=None):
        if not isinstance(other, int):
            raise NotImplementedError
        tmp_register = self._connection._get_inactive_register()
        add_operands = [
            tmp_register,
            tmp_register,
            Constant(other),
        ]
        if mod is None:
            add_instr = Instruction.ADD
        else:
            if not isinstance(mod, int):
                raise NotImplementedError
            add_instr = Instruction.ADDM
            add_operands.append(Constant(mod))

        commands = []
        with self._connection._activate_register(tmp_register):
            commands += self._get_load_commands(tmp_register)
            commands += [Command(
                instruction=add_instr,
                operands=add_operands,
            )]
            commands += self._get_store_commands(tmp_register)
        self._connection.put_commands(commands)

    def _get_load_commands(self, register):
        return self._get_access_commands(Instruction.LOAD, register)

    def _get_store_commands(self, register):
        return self._get_access_commands(Instruction.STORE, register)

    def _get_access_commands(self, instruction, register):
        assert instruction == Instruction.LOAD or instruction == Instruction.STORE, "Not an access instruction"
        commands = []
        if isinstance(self._index, Future):
            if self._connection is not self._index._connection:
                raise RuntimeError("Future-index must be from the same connection as the future itself")
            tmp_register = self._connection._get_inactive_register()
            # NOTE this might be many commands if the index is a future with a future index etc
            with self._connection._activate_register(tmp_register):
                access_index_cmds = self._index._get_access_commands(
                    instruction=Instruction.LOAD,
                    register=tmp_register,
                )
            commands += access_index_cmds
            index = tmp_register
        elif isinstance(self._index, int) or isinstance(self._index, Register):
            index = self._index
        else:
            raise TypeError(f"Cannot use type {type(self._index)} as index to load future")
        address_entry = parse_address(f"{Symbols.ADDRESS_START}{self._address}[{index}]")
        access_cmd = Command(
            instruction=instruction,
            operands=[
                register,
                address_entry,
            ],
        )
        commands.append(access_cmd)
        return commands

    def if_eq(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BEQ,
            a=self,
            b=other,
        )

    def if_ne(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BNE,
            a=self,
            b=other,
        )

    def if_lt(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BLT,
            a=self,
            b=other,
        )

    def if_ge(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BGE,
            a=self,
            b=other,
        )

    def if_ez(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BEZ,
            a=self,
            b=other,
        )

    def if_nz(self, other):
        return _IfContext(
            connection=self._connection,
            condition=Instruction.BNZ,
            a=self,
            b=other,
        )


class Array:
    def __init__(self, connection, length, address, init_values=None, lineno=None):
        if init_values is not None:
            if not all((isinstance(x, int) or x is None) for x in init_values):
                raise TypeError("Array needs to consist of int's or None's")
            length = len(init_values)
        assert isinstance(length, int) and length > 0, f"{length} is not a valid length"
        self._connection = connection
        self._length = length
        self._address = address
        self._init_values = init_values
        self._lineno = lineno

    @property
    def lineno(self):
        """What line in host application file initiated this array"""
        return self._lineno

    def __len__(self):
        return self._length

    def __getitem__(self, index):
        return self._connection._shared_memory.get_array_part(address=self._address, index=index)

    @property
    def address(self):
        return self._address

    def get_future_index(self, index):
        if isinstance(index, str):
            index = parse_register(index)
        return Future(
            connection=self._connection,
            address=self._address,
            index=index,
        )

    def get_future_slice(self, s):
        range_args = []
        for attr in ["start", "stop", "step"]:
            x = getattr(s, attr)
            if x is not None:
                if not isinstance(x, int):
                    raise NotImplementedError("Future slices can only be specified by integers at this point, "
                                              f"not {type(x)}")
                range_args.append(x)
        return [self.get_future_index(index) for index in range(*range_args)]

    def foreach(self):
        return _ForEachContext(
            connection=self._connection,
            array=self,
            return_index=False,
        )

    def enumerate(self):
        return _ForEachContext(
            connection=self._connection,
            array=self,
            return_index=True,
        )


class _Context:

    next_id = 0

    @property
    @abc.abstractmethod
    def ENTER_METH(self):
        pass

    @property
    @abc.abstractmethod
    def EXIT_METH(self):
        pass

    def __init__(self, connection, **kwargs):
        self._id = self._get_id()
        self._connection = connection
        self._kwargs = kwargs

    def _get_id(self):
        _Context.next_id += 1
        return _Context.next_id - 1

    def __enter__(self):
        return getattr(self._connection, self.ENTER_METH)(
            context_id=self._id,
            **self._kwargs,
        )

    def __exit__(self, *args, **kwargs):
        getattr(self._connection, self.EXIT_METH)(
            context_id=self._id,
            **self._kwargs,
        )


class _IfContext(_Context):

    ENTER_METH = '_enter_if_context'
    EXIT_METH = '_exit_if_context'

    def __init__(self, connection, condition, a, b):
        super().__init__(
            connection=connection,
            condition=condition,
            a=a,
            b=b,
        )


class _ForEachContext(_Context):

    ENTER_METH = '_enter_foreach_context'
    EXIT_METH = '_exit_foreach_context'

    def __init__(self, connection, array, return_index):
        super().__init__(
            connection=connection,
            array=array,
            return_index=return_index,
        )