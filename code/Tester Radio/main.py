import board
import busio
import digitalio
import time

import adafruit_rfm9x

#####  Initialization  #######
ANTENNA_ATTACHED = True

RADIO_FREQ_MHZ = 433.0
cs = digitalio.DigitalInOut(board.D5)
reset = digitalio.DigitalInOut(board.D6)
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

LED = digitalio.DigitalInOut(board.D13)
LED.direction = digitalio.Direction.OUTPUT

radio = adafruit_rfm9x.RFM9x(spi, cs, reset, 433)
radio.low_datarate_optimize = True

####  Initialization End #####

#Building message to send out
finalMessage = b'\xee\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa'
# b'\xcc\xaa'
print(finalMessage)

# transmits a signal
while True:

    print("Sending Message")
    radio.send(finalMessage, keep_listening=True)
    listenAgain = True

    time.sleep(2)

