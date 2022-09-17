"""
`ftp`
====================================================

Simple CircuitPython compatible file transfer protocol

* Author(s): 
 - Flynn Dreilinger

Implementation Notes
--------------------

"""
import os
import math

class FileTransferProtocol:

    def __init__(self, ptp, log=False):
        self.ptp = ptp
        self.log = log
        self.request_file_cmd = 's'
        self.request_partial_file_cmd = 'e'
        self.chunk_size = 245

    async def request_file(self, remote_path, local_path, retries=3):
        if self.log: print("PyCubed requesting file now")
        await self.ptp.send_packet(
            self.ptp.cmd_packet,
            [self.request_file_cmd, remote_path],
        )
        missing = await self.receive_file(local_path)
       
        while retries:
            if self.log: print(f"missing: {missing}")
            if self.log: print(f"retries remaining: {retries}")
            if missing == set():
                return True
            self.ptp.send_packet(
                self.ptp.cmd_packet,
                [self.request_partial_file_cmd, remote_path, list(missing)]
            )
            missing = await self.receive_partial_file(local_path, missing)
            retries -= 1
        return False

    async def receive_file(self, local_path):
        num_packets, sequence_number = await self.ptp.receive_packet()
        num_packets = abs(num_packets)
        if self.log: print(f"expecting to receive {num_packets} packets")
        with open(local_path, 'ab+') as f:
            missing = {i for i in range(num_packets)}
            for packet_num in range(num_packets):
                chunk, packet_num_recvc  = await self.ptp.receive_packet()
                missing.remove(packet_num_recvc)
                f.write(chunk)
                os.sync()
            return missing
    
    async def receive_file_sync(self, local_path):
        num_packets, sequence_number = self.ptp.receive_packet_sync()
        num_packets = abs(num_packets)
        if self.log: print(f"expecting to receive {num_packets} packets")
        with open(local_path, 'ab+') as f:
            missing = {i for i in range(num_packets)}
            for packet_num in range(num_packets):
                chunk, packet_num_recvc  = self.ptp.receive_packet_sync()
                missing.remove(packet_num_recvc)
                f.write(chunk)
                os.sync()
            return missing

    async def receive_partial_file(self, local_path, missing):
        _, _ = await self.ptp.receive_packet()
        missing_immutable = tuple(missing)
        for expected_packet_num in missing_immutable:
            chunk, recv_packet_num  = await self.ptp.receive_packet()
            missing.remove(int(recv_packet_num))
            location = self.packet_size * recv_packet_num
            self.insert_into_file(chunk, local_path, location)
            os.sync()
        return missing

    def insert_into_file(self, data, filename, location):
        """Insert data into a file, and be worried about running out of RAM
        """
        with open(filename, 'rb+') as fh:
            fh.seek(location)
            with open('tmpfile', 'wb+') as th:
                for chunk, _ in self._read_chunks(fh, self.chunk_size): 
                    print(chunk)
                    th.write(chunk)
                fh.seek(location)
                fh.write(data)
        
        with open(filename, 'ab+') as fh:
            fh.seek(location + len(data))
            with open('tmpfile', 'rb+') as th:
                for chunk, _ in self._read_chunks(th, self.chunk_size): 
                    print(chunk)
                    fh.write(chunk)
        os.remove('tmpfile')

    async def send_file(self, filename):
        """Send a file

        Args:
            filename (str): path to file that will be sent
            chunk_size (int, optional): chunk sizes that will be sent. Defaults to 64.
        """
        with open(filename, 'rb') as f:
            stats = os.stat(filename)
            filesize = stats[6]
            
            # send the number of packets for the client
            print("sending number of packets!!!!!")
            await self.ptp.send_packet(
                self.ptp.data_packet,
                 - math.ceil(filesize / self.chunk_size)
            )

            # send all the chunks
            for chunk, packet_num in self._read_chunks(f, self.chunk_size):
                await self.ptp.send_packet(
                    self.ptp.data_packet,
                    chunk,
                    packet_num
                )

    def send_file_sync(self, filename):
        """Send a file

        Args:
            filename (str): path to file that will be sent
            chunk_size (int, optional): chunk sizes that will be sent. Defaults to 64.
        """
        with open(filename, 'rb') as f:
            stats = os.stat(filename)
            filesize = stats[6]
            
            # send the number of packets for the client
            print("sending number of packets!!!!!")
            self.ptp.send_data_packet_sync(
                 - math.ceil(filesize / self.chunk_size)
            )

            # send all the chunks
            for chunk, packet_num in self._read_chunks(f, self.chunk_size):
                self.ptp.send_data_packet_sync(
                    chunk,
                    packet_num
                )
                
    def _read_chunks(self, infile, chunk_size):
        """Generator that reads chunks of a file

        Args:
            infile (str): path to file that will be read
            chunk_size (int, optional): chunk sizes that will be returned. Defaults to 64.

        Yields:
            bytes: chunk of file
        """
        counter = 0
        while True:
            chunk = infile.read(chunk_size)
            if chunk:
                yield (chunk, counter)
            else:
                break
            counter += 1
