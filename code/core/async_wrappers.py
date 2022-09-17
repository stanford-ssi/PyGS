class RadioProtocol:

    def __init__(self, radio):
        self.radio = radio

    def write(self, packet):
        # break into < 250 characters
        num_packets = math.ceil(len(packet)/250)
        if num_packets != 1:
            print("TRYING TO SEND MPP")
        for i in range(num_packets):
            self.radio.send(packet[i*250:(i+1)*250])

    async def readline(self):
        packet = b''
        while True:
            radio_packet = await self.radio.await_rx()
            if not radio_packet:
                yield
                continue
            print(f"received radio packet: {radio_packet}") # ({type(radio_packet)})")
            if '\n' in radio_packet:
                break
            else:
                print("RCVD PKT W/O \n")
            packet += radio_packet # check this
        return packet

    def readline_sync(self):
        packet = self.radio.receive(timeout=10)
        return packet
        