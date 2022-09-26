import binascii
import io

import msgpack


class AsyncPacketTransferProtocol:
    """A simple transfer protocol for commands and data"""

    def __init__(self, protocol, packet_size=252, log=False):
        self.protocol = protocol
        self.packet_size = 252
        self.log = log
        self.tmp_stream = io.BytesIO()
        self.out_stream = io.BytesIO()
        self.data_packet = 0
        self.cmd_packet = 1
        self.header_len = 3
        self.max_packet_total_size = 252
        self.max_data_len = self.max_packet_total_size - self.header_len

    def write_packet_into_out_stream(self, packet_type, payload, sequence_num):
        self.out_stream.seek(0)
        self.tmp_stream.seek(0)
        if packet_type != self.cmd_packet and packet_type != self.data_packet:
            return -1
        elif sequence_num > 2**15 - 1:
            return -1
        else:
            msgpack.pack(payload, self.tmp_stream)
            payload_len = self.tmp_stream.tell()
            self.tmp_stream.seek(0)
            if payload_len > self.max_data_len:
                return -1
            header = (packet_type << 23) | (payload_len << 15) | sequence_num
            if self.log:
                print(f"header: {header}")
            if self.log:
                print(f"packet type: {packet_type}")
            if self.log:
                print(f"payload len: {payload_len}")
            if self.log:
                print(f"sequence num: {sequence_num}")
            if self.log:
                print(f"pycubed sending packet: {self.tmp_stream.getvalue()}")
            header_arr = bytearray(3)
            header_arr[0] = (header >> 2 * 8) & 0xFF
            header_arr[1] = header >> 8 & 0xFF
            header_arr[2] = header & 0xFF
            self.out_stream.write(header_arr)
            self.out_stream.write(self.tmp_stream.read(payload_len))
            self.out_stream.seek(0)
            self.tmp_stream = io.BytesIO()  # TODO fix this.
            self.tmp_stream.seek(0)
            return payload_len

    def send_cmd_packet_sync(self, command):
        payload_len = self.write_packet_into_out_stream(
            self.cmd_packet, command, 2**15-1
        )
        if payload_len == -1:
            return False
        self.out_stream.seek(0)
        if self.log:
            print(f"wrote data: {self.out_stream.read(252)}")
        self.out_stream.seek(0)
        success = self.protocol.send_with_ack(self.out_stream.read(252))
        if self.log:
            print("waiting for ack...")
        if not success:
            if self.log:
                print("did not receive ack")
            return False
        if self.log:
            print("received ack")

    def send_data_packet_sync(self, payload, sequence_num=2**15 - 1):
        payload_len = self.write_packet_into_out_stream(
            self.data_packet, payload, sequence_num
        )
        if payload_len == -1:
            return False
        self.out_stream.seek(0)
        if self.log:
            print(f"wrote data: {self.out_stream.read(252)}")
        self.out_stream.seek(0)
        self.protocol.send(self.out_stream.read(252))
        self.out_stream.seek(0)
        return True

    async def send_packet(self, packet_type, payload, sequence_num=2**15 - 1):
        payload_len = self.write_packet_into_out_stream(
            packet_type, payload, sequence_num
        )
        if payload_len == -1:
            return False
        if packet_type == self.cmd_packet:
            self.out_stream.seek(0)
            if self.log:
                print(f"wrote data: {self.out_stream.read(252)}")
            self.out_stream.seek(0)
            success = await self.protocol.send_with_ack(self.out_stream.read(252))
            if self.log:
                print("waiting for ack...")
            if not success:
                if self.log:
                    print("did not receive ack")
                return False
            if self.log:
                print("received ack")
        else:
            self.out_stream.seek(0)
            if self.log:
                print(f"wrote data: {self.out_stream.read(252)}")
            self.out_stream.seek(0)
            self.protocol.send(self.out_stream.read(252))
        self.out_stream.seek(0)
        return True

    async def receive_packet(self):
        data = await self.protocol.read(3)
        if data is None:
            return False, False
        header_arr = bytearray(data)
        header = int.from_bytes(header_arr[0:3], "big")
        packet_type = header >> 23
        payload_len = (header >> 15) & (2**8 - 1)
        sequence_num = header & (2**15 - 1)
        if self.log:
            print(f"header: {header}")
        if self.log:
            print(f"packet type: {packet_type}")
        if self.log:
            print(f"payload len: {payload_len}")
        if self.log:
            print(f"sequence num: {sequence_num}")
        self.tmp_stream = io.BytesIO()
        if self.log:
            print(f"tmp stream before rw: {self.tmp_stream.getvalue()}")
        self.tmp_stream.seek(0)
        payload_pack_success = await self.protocol.read_into_stream(
            payload_len, self.tmp_stream
        )
        if self.log:
            print(f"tmp stream before write: {self.tmp_stream.getvalue()}")
        self.tmp_stream.seek(0)
        if self.log:
            print(f"payload_packed: {self.tmp_stream.read(payload_len)}")
        self.tmp_stream.seek(0)
        try:
            payload = msgpack.unpack(self.tmp_stream)  # TODO make this the same?
        except TypeError:
            print(f"Unexpected structure: {self.tmp_stream.getvalue()}")
            return False, False
        except ValueError:
            print(f"Failed to decode: {self.tmp_stream.getvalue()}")
            return False, False
        except Exception as e:
            print(f"Unknown exception: {self.tmp_stream.getvalue()} {e}")
            return False, False
        else:
            if packet_type == self.cmd_packet:
                print("pycubed sending ACK")
                self.protocol.send(b"ACK")
            self.tmp_stream = io.BytesIO()
            self.tmp_stream.seek(0)
            if self.log:
                print(f"payload: {payload}")
            return payload, sequence_num
        finally:
            self.tmp_stream = io.BytesIO()
            self.tmp_stream.seek(0)

    def crc32(self, packet_type, payload):
        packet_bytes = b""
        if isinstance(payload, int):
            packet_bytes = str(payload).encode("ascii")
        elif isinstance(payload, list):
            packet_bytes = str(payload).encode("ascii")
        elif isinstance(payload, bytes):
            packet_bytes = payload
        elif isinstance(payload, str):
            packet_bytes = payload.encode("ascii")
        return binascii.crc32(packet_bytes, 0).to_bytes(4, "big")
