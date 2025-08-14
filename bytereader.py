import io
import struct

class ByteReader:
    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)

    def read_bytes(self, size) -> bytes:
        return self.buffer.read(size)

    def read_byte(self) -> int:
        return struct.unpack("<B", self.buffer.read(1))[0]

    def read_short(self) -> int:
        return struct.unpack("<h", self.buffer.read(2))[0]
    
    def read_long(self) -> int:
        return struct.unpack("<i", self.buffer.read(4))[0]

    def read_float(self) -> float:
        return struct.unpack("<f", self.buffer.read(4))[0]

    def read_string(self, encoding="utf-8") -> str:
        chars = []
        while True:
            b = self.buffer.read(1)
            if not b or b == b'\x00':
                break
            chars.append(b)
        return b''.join(chars).decode(encoding, errors='ignore')

    def tell(self) -> int:
        return self.buffer.tell()

    def seek(self, pos: int):
        self.buffer.seek(pos)

    def remaining(self) -> int:
        current = self.buffer.tell()
        self.buffer.seek(0, io.SEEK_END)
        end = self.buffer.tell()
        self.buffer.seek(current)
        return end - current