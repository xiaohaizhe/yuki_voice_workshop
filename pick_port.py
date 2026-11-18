from __future__ import annotations

import socket


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


for candidate in range(8765, 8776):
    if port_is_free(candidate):
        print(candidate)
        break
else:
    print(0)
