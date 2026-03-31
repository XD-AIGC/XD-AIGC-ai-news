"""Minimal HTTP/HTTPS forward proxy server.

Usage:
    python http_proxy.py [--port 7890]

Listens on 0.0.0.0 so LAN clients (e.g. the collection server) can use it.
"""

import argparse
import socket
import threading
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("proxy")

BUFFER_SIZE = 65536
CONNECT_TIMEOUT = 30
SOCK_TIMEOUT = 300  # 5 min read/write timeout for long-running API calls


def _configure_sock(sock: socket.socket):
    """Set keepalive and timeout on a connected socket."""
    sock.settimeout(SOCK_TIMEOUT)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)


def handle_connect(client_sock: socket.socket, host: str, port: int):
    """Handle HTTPS CONNECT tunnel."""
    try:
        remote_sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
    except Exception as e:
        log.warning("CONNECT %s:%s failed: %s", host, port, e)
        client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        client_sock.close()
        return

    _configure_sock(remote_sock)
    _configure_sock(client_sock)
    client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    _tunnel(client_sock, remote_sock)


def handle_http(client_sock: socket.socket, method: str, url: str, rest: bytes):
    """Handle plain HTTP request by forwarding."""
    # url: http://host:port/path
    try:
        if url.startswith("http://"):
            url_body = url[7:]
        else:
            url_body = url
        slash = url_body.find("/")
        if slash == -1:
            host_port = url_body
            path = "/"
        else:
            host_port = url_body[:slash]
            path = url_body[slash:]

        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            port = int(port)
        else:
            host = host_port
            port = 80

        remote_sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        _configure_sock(remote_sock)
        _configure_sock(client_sock)
        # Rebuild request with relative path
        first_line = f"{method} {path} HTTP/1.1\r\n".encode()
        remote_sock.sendall(first_line + rest)
        _tunnel(client_sock, remote_sock)
    except Exception as e:
        log.warning("HTTP %s failed: %s", url, e)
        client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        client_sock.close()


def _tunnel(sock1: socket.socket, sock2: socket.socket):
    """Bi-directional forwarding between two sockets."""

    def forward(src, dst):
        try:
            while True:
                data = src.recv(BUFFER_SIZE)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except Exception:
                pass

    t1 = threading.Thread(target=forward, args=(sock1, sock2), daemon=True)
    t2 = threading.Thread(target=forward, args=(sock2, sock1), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    sock1.close()
    sock2.close()


def handle_client(client_sock: socket.socket, addr):
    try:
        data = client_sock.recv(BUFFER_SIZE)
        if not data:
            client_sock.close()
            return

        first_line_end = data.find(b"\r\n")
        first_line = data[:first_line_end].decode("utf-8", errors="replace")
        rest = data[first_line_end + 2:]

        parts = first_line.split()
        if len(parts) < 3:
            client_sock.close()
            return

        method, target, _ = parts[0], parts[1], parts[2]

        if method.upper() == "CONNECT":
            # CONNECT host:port HTTP/1.1
            if ":" in target:
                host, port = target.rsplit(":", 1)
                port = int(port)
            else:
                host, port = target, 443
            log.info("%s CONNECT %s:%s", addr[0], host, port)
            handle_connect(client_sock, host, port)
        else:
            log.info("%s %s %s", addr[0], method, target)
            handle_http(client_sock, method, target, rest)
    except Exception as e:
        log.error("Error handling %s: %s", addr, e)
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Simple HTTP/HTTPS proxy")
    parser.add_argument("--port", type=int, default=7890)
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(128)
    log.info("Proxy listening on 0.0.0.0:%d", args.port)

    try:
        while True:
            client_sock, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        server.close()


if __name__ == "__main__":
    main()
