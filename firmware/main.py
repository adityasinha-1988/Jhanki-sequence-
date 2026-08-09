"""
main.py — runs after boot.py.
Initializes the MCP23017 over I2C, sets all 16 expanded pins as outputs,
then hosts a lightweight raw-socket HTTP server that listens for:

    GET /<channel_id>/on      channel_id = 1-16
    GET /<channel_id>/off

and drives the matching MCP23017 pin HIGH (on) or LOW (off), which in turn
triggers the corresponding relay on the 16-channel high-level-trigger board.
"""

import socket
import time
from machine import I2C, Pin

from mcp23017 import MCP23017

# --------------------------------------------------------------------------
# Hardware setup
# --------------------------------------------------------------------------

I2C_SCL_PIN = 22    # <-- adjust to your wiring
I2C_SDA_PIN = 21    # <-- adjust to your wiring
MCP_ADDRESS = 0x20  # default MCP23017 address with A0-A2 tied to GND

i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
mcp = MCP23017(i2c, address=MCP_ADDRESS)
mcp.set_all_outputs()
mcp.all_off()

print("MCP23017 initialized, all 16 channels OFF.")

# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

SERVER_PORT = 80


def parse_request(request_line):
    """
    Parses a line like: GET /7/on HTTP/1.1
    Returns (channel_id:int, action:str) or (None, None) if it doesn't match.
    """
    try:
        parts = request_line.split(" ")
        if len(parts) < 2 or parts[0] != "GET":
            return None, None
        path = parts[1].strip("/")
        segments = path.split("/")
        if len(segments) != 2:
            return None, None
        channel_id = int(segments[0])
        action = segments[1].lower()
        if action not in ("on", "off"):
            return None, None
        if not 1 <= channel_id <= 16:
            return None, None
        return channel_id, action
    except (ValueError, IndexError):
        return None, None


def handle_client(conn):
    try:
        request = conn.recv(1024).decode("utf-8")
        if not request:
            conn.close()
            return

        request_line = request.split("\r\n")[0]
        channel_id, action = parse_request(request_line)

        if channel_id is not None:
            pin_index = channel_id - 1  # channel 1 -> pin 0, ... channel 16 -> pin 15
            mcp.set_pin(pin_index, 1 if action == "on" else 0)
            body = "channel %d %s" % (channel_id, action.upper())
            status_line = "HTTP/1.1 200 OK"
            print(body)
        else:
            body = "bad request"
            status_line = "HTTP/1.1 400 Bad Request"

        response = (
            status_line + "\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: " + str(len(body)) + "\r\n"
            "Connection: close\r\n"
            "\r\n" + body
        )
        conn.send(response)
    except Exception as exc:
        print("Error handling client:", exc)
    finally:
        conn.close()


def start_server():
    addr = socket.getaddrinfo("0.0.0.0", SERVER_PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    print("Relay server listening on port %d" % SERVER_PORT)

    while True:
        try:
            conn, remote_addr = s.accept()
            handle_client(conn)
        except OSError as exc:
            print("Socket error:", exc)
            time.sleep(0.5)


start_server()
