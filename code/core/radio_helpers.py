import digitalio
import board
import time
import alarm
import pycubed_rfm9x
import adafruit_requests
import rtc
from microcontroller import cpu
from analogio import AnalogIn
from core.async_wrappers import RadioProtocol
from ptp import AsyncPacketTransferProtocol
from ftp import FileTransferProtocol
from gs_config import config
from core.scriptRunner import runScript
from secrets import secrets

FIFO = bytearray(256)
fifo_view = memoryview(FIFO)

ID = config['ID']
STATUS_TOPIC =  secrets['status'] + ID
REMOTE_TOPIC =  secrets['remote'] + ID

sendMSG = False # A flag to send a radio signal after initialization 

def mqtt_message(client, topic, payload):
    print("[{}] {}".format(topic, payload))
    try:
        if payload[:7] == 'PUBLISH':
            argsList = payload[8:].split(' ', 1) # Cuts off space as well
            topic = argsList[0]
            message = argsList[1]
            client.publish(topic, message)
        elif payload[:4] == 'EXEC':
            exec(payload[5:])
        elif payload[:3] == 'RUN': # Just file name, no file type extension
            program = payload[4:]
            runScript(program)
        elif payload[:4] == 'SEND': 
            # TODO: Need to see if this is going to be a general send signal or one directly to sapling
            # Need to see how sapling is going to communicate. Whether it also sets radio nodes. 
            # I believe that it also sends packages in a json format, which we'll need to decode
            GS.send_message(payload[5:], client)
        elif payload[:4] == 'PING':
            message = "You pinged ground station {0}. This is the local time: {1}".format(config['ID'], time.time())
            client.publish(REMOTE_TOPIC, message)
    except Exception as err:
        print('error: {}'.format(err))
        client.publish(REMOTE_TOPIC, err)

def subscribe(mqtt_client, userdata, topic, granted_qos):
    # This method is called when the mqtt_client subscribes to a new feed.
    print("Subscribed to {0} with QOS level {1}".format(topic, granted_qos))


def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to MQTT broker!")

class GroundStation:
    myuid = int.from_bytes(cpu.uid, 'big')
    last_rssi = 0

    SATELLITE = {
        # 436.703
        'NORBI': {'NAME': 'NORBI', 'FREQ': 436.703, 'SF': 10, 'BW': 250000, 'CR': 8, 'BR': 1320000},
        'VR3X': {'NAME': 'VR3X', 'FREQ': 915.6, 'SF': 7, 'BW': 62500, 'CR': 8, 'BR': 1320000},
        'RADIO': {'NAME': 'RADIO', 'FREQ': 433.0, 'SF': 7, 'BW': 125000, 'CR': 5, 'BR': 5000000}, # default values
        'SAPLING': {'NAME': 'SAPLING', 'FREQ': 437.4, 'SF': 7, 'BW': 125000, 'CR': 8, 'BR': 1320000}
    }

    def __init__(self):
        self.vbatt = AnalogIn(board.IO17)
        LED = digitalio.DigitalInOut(board.LED)
        LED.switch_to_output(True)
        self.spi = board.SPI()
        self.R1_CS = digitalio.DigitalInOut(board.D5)
        self.R2_CS = digitalio.DigitalInOut(board.D20)
        self.R3_CS = digitalio.DigitalInOut(board.D12)
        self.R1_CS.switch_to_output(True)
        self.R2_CS.switch_to_output(True)
        self.R3_CS.switch_to_output(True)
        self._BUFFER = bytearray(256)

        self.radios = None
        self.id = None
        self.mqtt_client = None

    @property
    def battery_voltage(self):
        _v = 0
        for _ in range(20):
            _v += self.vbatt.value
        _v = 2*((_v/20)*3.3/65536)
        return _v

    def init_radios(self, config):
        # define radio pins
        # 1 - RST:B(D61/D6) CS:C(DAC0/D5)  IRQ:IO5
        R1_RST = digitalio.DigitalInOut(board.D6)
        R1_RST.switch_to_output(True)
        # 2 - RST:D(A7/D21) CS:E(A8/D20)   IRQ:IO6
        R2_RST = digitalio.DigitalInOut(board.D21)
        R2_RST.switch_to_output(True)
        # 3 - RST:D59/D12   CS:DAC1/D13    IRQ:IO7
        R3_RST = digitalio.DigitalInOut(board.D13)
        R3_RST.switch_to_output(True)

        # initialize radios
        radio1 = pycubed_rfm9x.RFM9x(
            board.SPI(), self.R1_CS, R1_RST, config['FREQ'])
        radio2 = pycubed_rfm9x.RFM9x(
            board.SPI(), self.R2_CS, R2_RST, config['FREQ'])
        radio3 = pycubed_rfm9x.RFM9x(
            board.SPI(), self.R3_CS, R3_RST, config['FREQ'])
        radio1.name = 1
        radio2.name = 2
        radio3.name = 3

        self.radios = (radio1, radio2, radio3)

        # configure radios
        for r in self.radios:
            r.node = 0xAB  # ground station ID (Sat sends to all, so it doesnt matter)
            r.destination = 0xFA # target sat's radiohead ID (Sat accepts all, so it doesn't matter)
            r.idle()

            # The two variables below need to be commented out if we want to test with our own radios
            # NOTE: Maybe this values are why we get crc errors. Moreover, when these weren't commented out for NORBI,
            # it didnt receive a signal. Until I commented them out and reloaded.
            r.spreading_factor = config['SF']
            r.signal_bandwidth = config['BW']
            r.baudrate = config['BR']  # added this
            r.coding_rate = config['CR']
            r.preamble_length = 8
            r.enable_crc = False
            # if getting crc error change this to false
            r.low_datarate_optimize = False
            r.ack_wait = 2
            r.ack_delay = 0.2
            r.ack_retries = 0


            r.r_aptp = AsyncPacketTransferProtocol(r)
            #r.outbox = r.r_aptp.outbox
            #r.inbox = r.r_aptp.inbox
            r.r_ftp = FileTransferProtocol(r.r_aptp)
        

        if sendMSG:
            self.send_message("Sending signal on radio init")

        return self.radios

    @property
    def counter(self):
        return int.from_bytes(alarm.sleep_memory[0:2], 'big')

    @counter.setter
    def counter(self, value):
        alarm.sleep_memory[0:2] = int(value % 65536).to_bytes(2, 'big')

    @property
    def msg_count(self):
        return int.from_bytes(alarm.sleep_memory[2:4], 'big')

    @msg_count.setter
    def msg_count(self, value):
        alarm.sleep_memory[2:4] = int(value % 65536).to_bytes(2, 'big')

    @property
    def msg_cache(self):
        return alarm.sleep_memory[4]

    @msg_cache.setter
    def msg_cache(self, value):
        alarm.sleep_memory[4] = value

    @property
    def deep_sleep(self):
        return int.from_bytes(alarm.sleep_memory[5:7], 'big')

    @deep_sleep.setter
    def deep_sleep(self, value):
        alarm.sleep_memory[5:7] = int(value % 65536).to_bytes(2, 'big')

    def _read_into(self, radio_cs, address, buf, length=None):
        if length is None:
            length = len(buf)
        self._BUFFER[0] = address & 0x7F  # Strip out top bit to set read value
        radio_cs.value = False
        self.spi.try_lock()
        self.spi.write(bytes([(address & 0x7F)]))
        self.spi.readinto(buf, end=length)
        radio_cs.value = True
        self.spi.unlock()
        # print(buf)

    def _read_u8(self, radio_cs, address):
        self._read_into(radio_cs, address, self._BUFFER, 1)
        return self._BUFFER[0]

    def _write_u8(self, radio_cs, address, val):
        radio_cs.value = False
        self.spi.try_lock()
        self._BUFFER[0] = (address | 0x80) & 0xFF  # Set top bit to 1
        self._BUFFER[1] = val & 0xFF
        self.spi.write(self._BUFFER, end=2)
        radio_cs.value = True
        self.spi.unlock()

    def rx_done(self, radio_cs):
        return (self._read_u8(radio_cs, 0x12) & 0x40) >> 6

    def is_crc(self, radio_cs):
        return not (self._read_u8(radio_cs,0x12) & 0x20) >> 5
    
    def clear_irq(self, radio_cs):
        self._write_u8(radio_cs, 0x12, 0xFF)

    def set_to_idle(self, radio_cs):
            self.last_rssi = self._read_u8(radio_cs, 0x1A)-164
            # put into idle mode
            reg = self._read_u8(radio_cs, 0x01)
            reg &= ~7  # mask
            reg |= (1 & 0xFF)  # standby
            self._write_u8(radio_cs, 0x01, reg)

    def get_msg2(self, radio_cs):
        # hacky way of reading radio RX buffer without reinitalizing the radios

        if not self.rx_done(radio_cs):
            pass
        else:
            packet = None
            error = 1
            self.set_to_idle(radio_cs)
            #if not (self._read_u8(radio_cs,0x12) & 0x20) >> 5:
            if not self.is_crc(radio_cs): # same as above
                l = self._read_u8(radio_cs, 0x13)  # fifo length
                # print(l)
                if l:
                    pos = self._read_u8(radio_cs, 0x10)
                    self._write_u8(radio_cs, 0x0D, pos)
                    packet = fifo_view[:l]
                    self._read_into(radio_cs, 0, packet)
                error = 0
            else:
                print('crc error')
                yield b'CRC ERROR'
            # clear IRQ flags
            self.clear_irq(radio_cs)
            # start listening again TODO: Why do we want it to listen again? (Probably cause we want radios to listen again befoer shutdown (in this case before intitialization))
            reg = self._read_u8(radio_cs, 0x01)
            reg &= ~7  # mask
            reg |= (5 & 0xFF)  # RX mode
            self._write_u8(radio_cs, 0x01, reg)
            yield packet
                
    def send_message(self, message, client=None):
        log = ""
        print("Sending Message: {}".format(message))
        log += "Sending Message \n"

        status = False
        for r in self.radios:
            print("Radios")
            #Turn them all off so message doesn't bounce around
            for radio in self.radios:
                radio.idle()

            status = r.send(message, keep_listening=False)

            if status:
                print("Signal sent successfully on radio {}".format(r.name))
                log += "[log]Signal sent successfully on radio {}".format(r.name)
                break
            else:
                print("Radio {} failed to send message".format(r.name))
                log += "Radio {} failed to send message".format(r.name)
        if client != None:
            client.publish(REMOTE_TOPIC, log)
    
    def gs_listen(self):
        for r in self.radios:
            r.listen()

    def validate_beacon(self, payload): # TODO: Payload will probably be in bytes
        return 'Hello World!' == payload
    
    def gs_rx(self, time_out=30) -> (pycubed_rfm9x.RFM9x | None):
        '''
        asd
        '''

        end_time = time.monotonic() + time_out
        while time.monotonic() < end_time:
            for radio in self.radios:
                if radio.rx_done:
                    radio.idle()
                    packet = None
                    error = 1
                    if not self.is_crc(radio.cs): # same as above
                        l = self._read_u8(radio.cs, 0x13)  # fifo length
                        # print(l)
                        if l:
                            pos = self._read_u8(radio.cs, 0x10) # Address of packet
                            self._write_u8(radio.cs, 0x0D, pos) # Write into FIFO
                            packet = fifo_view[:l]
                            self._read_into(radio.cs, 0, packet)
                        error = 0
                    else:
                        print('crc error')
                    # clear IRQ flags
                    self.clear_irq(radio.cs)
                    # start listening again
                    radio.listen()
                    if self.validate_beacon(packet):
                        return radio
        return None

    def send_file(self, cmd, filename):
        # Below would wait to receieve a beackon
        # Set them all to listen
        self.gs_listen()

        # Listen for a beacon and grab first antenna to make contact
        radio = self.gs_rx()

        if radio is None:
            yield 'Error, no contact'
        else:
            ack = radio.send_with_ack(cmd)
            if ack is not None:
                if ack: print('ACK RSSI:',radio.last_rssi-137)

            num_packets, _ = await radio.r_aptp.receive_packet()
            missing = await radio.radio_ftp.receive_file(f'/sd/{filename}', num_packets)
            print(f"missing packets: {missing}")
            print("Received file!")

# TODO How does this work? Is it the same ground station instance no matter who imports it? Should we also use __name__ == __main__ ?
#gs = GroundStation()
GS = GroundStation()