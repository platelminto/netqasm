from netqasm.sdk import EPRSocket
from netqasm.sdk.external import NetQASMConnection, Socket, get_qubit_state


def main(app_config=None):
    log_config = app_config.log_config

    # Create a socket to recv classical information
    socket = Socket("receiver", "sender", log_config=log_config)

    # Create a EPR socket for entanglement generation
    epr_socket = EPRSocket("sender")

    # Initialize the connection
    receiver = NetQASMConnection(
        app_name=app_config.app_name,
        log_config=log_config,
        epr_sockets=[epr_socket]
    )
    with receiver:
        epr = epr_socket.recv()[0]
        receiver.flush()

        # Get the corrections
        msg = socket.recv()
        print(f"`receiver` got corrections: {msg}")
        m1, m2 = eval(msg)
        if m2 == 1:
            print("`receiver` will perform X correction")
            epr.X()
        if m1 == 1:
            print("`receiver` will perform Z correction")
            epr.Z()

        receiver.flush()
        # Get the qubit state
        # NOTE only possible in simulation, not part of actual application
        dm = get_qubit_state(epr)
        print(f"`receiver` recieved the teleported state {dm}")
        return {"qubit_state": dm if dm is None else dm.tolist()}


if __name__ == "__main__":
    main()