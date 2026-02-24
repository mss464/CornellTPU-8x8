#!/usr/bin/env python3
"""
Simple TPU RPC Server.

This script runs on the FPGA board. It initializes the TpuDriver and listens
on a TCP socket for remote commands from the host machine.
"""

import socket
import struct
import numpy as np
import argparse
import sys
import os

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from runtime.pynq_host import TpuDriver
except ImportError as e:
    print(f"Error importing TpuDriver: {e}")
    print("This script must be run on the PYNQ board environment.")
    sys.exit(1)

# Protocol Commands
CMD_RESET = 1
CMD_WRITE_BRAM = 2
CMD_READ_BRAM = 3
CMD_WRITE_INSTR = 4
CMD_COMPUTE = 5

# Responses
RESP_OK = 0
RESP_ERR = 1
RESP_DATA = 2

def recvall(sock, count):
    buf = b''
    while count:
        try:
            newbuf = sock.recv(count)
        except ConnectionResetError:
            return None
        if not newbuf: return None
        buf += newbuf
        count -= len(newbuf)
    return buf

def handle_client(conn, addr, tpu):
    print(f"Connected by {addr}")
    try:
        while True:
            # Read command (1 byte)
            cmd_data = recvall(conn, 1)
            if not cmd_data:
                break
            cmd = struct.unpack('!B', cmd_data)[0]

            if cmd == CMD_RESET:
                tpu.reset()
                conn.sendall(struct.pack('!B', RESP_OK))
                
            elif cmd == CMD_WRITE_BRAM:
                # header: addr (uint32), num_floats (uint32)
                hdr = recvall(conn, 8)
                bram_addr, num_floats = struct.unpack('!II', hdr)
                # data: num_floats * 4 bytes
                data = recvall(conn, num_floats * 4)
                arr = np.frombuffer(data, dtype=np.float32)
                tpu.write_bram(bram_addr, arr)
                conn.sendall(struct.pack('!B', RESP_OK))

            elif cmd == CMD_READ_BRAM:
                hdr = recvall(conn, 8)
                bram_addr, num_floats = struct.unpack('!II', hdr)
                arr = tpu.read_bram(bram_addr, num_floats)
                # Ensure it's dense, float32, little-endian
                data_bytes = arr.astype('<f4').tobytes()
                conn.sendall(struct.pack('!BI', RESP_DATA, len(data_bytes)))
                conn.sendall(data_bytes)

            elif cmd == CMD_WRITE_INSTR:
                hdr = recvall(conn, 8)
                base_addr, num_instr = struct.unpack('!II', hdr)
                data = recvall(conn, num_instr * 8)
                arr = np.frombuffer(data, dtype=np.uint64)
                tpu.write_instructions(arr, base_addr)
                conn.sendall(struct.pack('!B', RESP_OK))

            elif cmd == CMD_COMPUTE:
                tpu.compute()
                conn.sendall(struct.pack('!B', RESP_OK))

            else:
                print(f"Unknown command: {cmd}")
                conn.sendall(struct.pack('!B', RESP_ERR))
                break

    except Exception as e:
        print(f"Error handling client: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        print(f"Disconnected {addr}")

def main():
    parser = argparse.ArgumentParser(description="TPU RPC Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--bitstream", help="Path to bitstream (optional)")
    parser.add_argument("--mock", action="store_true", help="Use Mock TpuDriver (for x86 testing without hw)")
    args = parser.parse_args()

    print("Initializing TPU Driver...")
    try:
        if args.mock:
            print("WARNING: Starting in MOCK mode. Hardware is NOT physical.")
            from runtime.mock_tpu import MockTpuDriver
            tpu = MockTpuDriver()
        else:
            tpu = TpuDriver(bitstream=args.bitstream)
    except Exception as e:
        print(f"Failed to initialize TPU: {e}")
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', args.port))
    s.listen(1)
    print(f"Listening on port {args.port}...")

    try:
        while True:
            conn, addr = s.accept()
            handle_client(conn, addr, tpu)
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        s.close()
        tpu.reset()

if __name__ == "__main__":
    main()
