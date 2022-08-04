import wifi, socketpool, time, alarm
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from radio_helpers import gs, mqtt_message, connected, subscribe
from secrets import secrets
import storage, os, board, json
from binascii import hexlify
import time


gs.ID = "A"
DATA_TOPIC = "ssi/gs/messages"
STATUS_TOPIC = "ssi/gs/status/" + gs.ID
CTRL_TOPIC = "ssi/gs/remote/" + gs.ID

SAT = gs.SATELLITE["RADIO"]

radios = []
# if we haven't slept yet, init radios
if not alarm.wake_alarm:
    print("First boot")
    radios = gs.init_radios(SAT)
    # reset counters
    gs.counter = 0
    gs.msg_count = 0
    gs.msg_cache = 0
    gs.deep_sleep = 600
else:
    radios = {1: gs.R1_CS, 2: gs.R2_CS, 3: gs.R3_CS}


print(
    "Loop: {}, Total Msgs: {}, Msgs in Cache: {}, Vbatt: {:.1f}".format(
        gs.counter, gs.msg_count, gs.msg_cache, gs.battery_voltage
    )
)

# try connecting to wifi
print("Connecting to WiFi...")
try:
    wifi.radio.connect(ssid=secrets['homeSSID'], password=secrets['homePass'])
    #wifi.radio.connect(ssid="Stanford") # open network
    print("Signal: {}".format(wifi.radio.ap_info.rssi))
    # Create a socket pool
    pool = socketpool.SocketPool(wifi.radio)
    # sync out RTC from the web
    gs.synctime(pool)
except Exception as e:
    print("Unable to connect to WiFi: {}".format(e))
# check radios
new_messages = {}
if alarm.wake_alarm:
    # hacky way of checking the radios without initalizing the hardware
    for r in radios:
        if gs.rx_done(radios[r]):
            print(r, end=": ")
            for msg in gs.get_msg2(radios[r]):
                if msg is not None:
                    print("[{}] rssi:{}".format(bytes(msg), gs.last_rssi), end=", ")
                    if (msg == b'CRC ERROR'):
                        print("Failed crc check")
                        continue
                    else:
                        # radio, time, gs id, msg, rssi, new?
                        new_messages[r] = {
                            "Radio": r,
                            "Time": time.time(),
                            "ID": gs.ID,
                            "Hexlify MSG": hexlify(msg),
                            "Bytes MSG": str(bytes(msg)),
                            "RSSI": gs.last_rssi,
                            "N": 1,
                        }
                        print(new_messages[r])
                        print("passes crc check")
            print()
    print("Done checking")
    radios = gs.init_radios(SAT)

if new_messages:
    gs.msg_count = gs.msg_count + 1

# if we have wifi, connect to mqtt broker
if wifi.radio.ap_info is not None:
    # try:1069855917

    # Set up a MiniMQTT Client
    mqtt_client = MQTT.MQTT(
        broker=secrets["broker"],
        port=secrets["port"],
        socket_pool=pool,
        is_ssl=False
    )
    mqtt_client.on_connect = connected
    mqtt_client.on_message = mqtt_message
    mqtt_client.on_subscribe = subscribe

    status = {
        "Time": time.time(),
        "ID": gs.ID,
        "#": gs.counter,
        "MSG#": gs.msg_count,
        "MSG_Cache": gs.msg_cache,
        "Battery": gs.battery_voltage,
        "WiFi_RSSI": wifi.radio.ap_info.rssi,
    }


    mqtt_client.connect()
    
    mqtt_client.subscribe(CTRL_TOPIC)
    
    print("Sending status")
    message = "GS {} status: ".format(gs.ID) + json.dumps(status)
    mqtt_client.publish(STATUS_TOPIC, message)


    # send any cached messages
    if gs.msg_cache:
        with open("/data.txt", "r") as f:
            l = f.readline()
            while l:
                message = "Sending cached message: " + l.strip()
                mqtt_client.publish(DATA_TOPIC, message)
                l = f.readline()
        try:
            os.remove("/data.txt")
        except:
            pass
        gs.msg_cache = 0

    # send any new messages
    if new_messages:
        for msg in new_messages:
            print("Sending message")
            print(new_messages[msg])
            #mqtt_client.publish(DATA_TOPIC, new_messages[msg])
            message = "Message received: " + json.dumps(new_messages[msg])
            mqtt_client.publish(DATA_TOPIC, message)

    # check for mqtt remote messages
    queuedUp = None
    loopOnce = True
    waitTime = 20
    print("Waiting {} seconds for commands to be sent to ground station before processing".format(waitTime))
    mqtt_client.publish(CTRL_TOPIC, "Waiting {} seconds for commands to be sent to ground station before processing".format(waitTime))
    time.sleep(waitTime)

    while loopOnce or queuedUp != None:
        loopOnce = False
        try:
            queuedUp = mqtt_client.loop()
        except:
            print("Error on mqtt loop")
        else:
            print(queuedUp)
        time.sleep(2)
     
    mqtt_client.disconnect()

# if we can't connect, cache message
else:
    for msg in new_messages:
        new_messages[msg]["N"] = 0  # not new
        try:
            storage.remount("/", False)
            with open("/data.txt", "a") as f:
                f.write(json.dumps(new_messages[msg]) + "\n")
            storage.remount("/", True)
        except:
            print("Cant cache msg. Connected to usb?")
        gs.msg_cache = gs.msg_cache + 1

gs.counter = gs.counter + 1

print("Finished. Deep sleep until RX interrupt or {}s timeout...".format(gs.deep_sleep))
# wake up on IRQ or after deep sleep time
pin_alarm1 = alarm.pin.PinAlarm(pin=board.IO5, value=True, pull=False)  # radio1
pin_alarm2 = alarm.pin.PinAlarm(pin=board.IO6, value=True, pull=False)  # radio2
pin_alarm3 = alarm.pin.PinAlarm(pin=board.IO7, value=True, pull=False)  # radio3
time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + gs.deep_sleep)
alarm.exit_and_deep_sleep_until_alarms(time_alarm, pin_alarm1, pin_alarm2, pin_alarm3)
