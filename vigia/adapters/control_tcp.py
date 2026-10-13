"""Porta de controle TCP 7765 das Ether Dream."""
from __future__ import annotations

import socket
from contextlib import contextmanager

from ..application.ports import ControlError
from ..domain.dac import Control, FirmwareNote
from ..domain.protocol import (CONTROL_PORT, RESPONSE_SIZE, VERSION_SIZE, ClearReply, clear_outcome, decode_version,
                               version_unsupported)


def recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("a DAC fechou a conexão")
        buf += chunk
    return buf


class TcpControlChannel:
    """Conecta, lê a saudação, envia um comando e desconecta.

    ATENÇÃO: na ED4 uma conexão nova interrompe o stream em andamento. A ED2/ED3 aceita um
    host por vez e recusa os demais. O Monitor só chama isto com a DAC parada ou por clique.
    """

    def __init__(self, timeout: float = 1.0, port: int = CONTROL_PORT):
        self.timeout, self.port = timeout, port

    @contextmanager
    def _session(self, ip: str):
        try:
            with socket.create_connection((ip, self.port), timeout=self.timeout) as conn:
                hello = recv_exact(conn, RESPONSE_SIZE)  # boas-vindas: 'a', '?', dac_status
                yield conn, hello
        except socket.timeout as e:
            raise ControlError(Control.NO_ANSWER) from e
        except OSError as e:  # recusada, resetada ou fechada logo após conectar
            raise ControlError(Control.REFUSED) from e

    def read_firmware(self, ip: str) -> str | FirmwareNote:
        with self._session(ip) as (conn, _hello):
            conn.sendall(b"v")
            resp = recv_exact(conn, RESPONSE_SIZE)
            if version_unsupported(resp):
                return FirmwareNote.NO_VERSION
            return decode_version(resp + recv_exact(conn, VERSION_SIZE - RESPONSE_SIZE))

    def clear_estop(self, ip: str) -> ClearReply:
        with self._session(ip) as (conn, hello):
            conn.sendall(b"c")
            return clear_outcome(hello, recv_exact(conn, RESPONSE_SIZE))
