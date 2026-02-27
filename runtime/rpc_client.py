import socket
import struct
import numpy as np

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

class RemoteTpuDriver:
    """Drop-in replacement for TpuDriver that communicates over TCP to the remote FPGA."""
    
    def __init__(self, host: str, port: int = 8080):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

    def __del__(self):
        try:
            self.sock.close()
        except:
            pass

    def _recvall(self, count):
        buf = b''
        while count:
            newbuf = self.sock.recv(count)
            if not newbuf:
                raise ConnectionError("Connection closed by server")
            buf += newbuf
            count -= len(newbuf)
        return buf

    def _wait_for_ok(self):
        resp = self._recvall(1)
        status = struct.unpack('!B', resp)[0]
        if status != RESP_OK:
            raise RuntimeError(f"Server returned error status: {status}")

    def reset(self):
        self.sock.sendall(struct.pack('!B', CMD_RESET))
        self._wait_for_ok()

    def write_bram(self, addr: int, values: np.ndarray):
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        data = values.astype('<f4').tobytes()
        
        # command, addr, len
        header = struct.pack('!BII', CMD_WRITE_BRAM, addr, len(values))
        self.sock.sendall(header + data)
        self._wait_for_ok()

    def read_bram(self, addr: int, length: int) -> np.ndarray:
        header = struct.pack('!BII', CMD_READ_BRAM, addr, length)
        self.sock.sendall(header)
        
        resp = self._recvall(5) # status (1 byte) + data len (4 bytes)
        status, data_len = struct.unpack('!BI', resp)
        if status != RESP_DATA:
            raise RuntimeError(f"Expected data response, got {status}")
            
        data = self._recvall(data_len)
        return np.frombuffer(data, dtype=np.float32).copy()

    def write_instructions(self, instructions: np.ndarray, base_addr: int = 0):
        instructions = np.asarray(instructions, dtype=np.uint64)
        data = instructions.astype('<u8').tobytes()
        
        header = struct.pack('!BII', CMD_WRITE_INSTR, base_addr, len(instructions))
        self.sock.sendall(header + data)
        self._wait_for_ok()

    def compute(self):
        self.sock.sendall(struct.pack('!B', CMD_COMPUTE))
        self._wait_for_ok()
