import wifi, socketpool, time, alarm, rtc
import adafruit_requests
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from core.radio_helpers import mqtt_message, connected, subscribe, GS
from secrets import secrets
from gs_config import config
import storage, os, board, json
from binascii import hexlify
import time


ID = config['ID']
SAT = GS.SATELLITE[config['SAT']]
DATA_TOPIC = secrets['data']
STATUS_TOPIC =  secrets['status'] + ID
REMOTE_TOPIC =  secrets['remote'] + ID

def synctime(pool):
    try:
        requests = adafruit_requests.Session(pool)
        TIME_API = "http://worldtimeapi.org/api/ip"
        the_rtc = rtc.RTC()
        response = None
        while True:
            try:
                print("Fetching time")
                # print("Fetching json from", TIME_API)
                response = requests.get(TIME_API)
                break
            except (ValueError, RuntimeError) as e:
                print("Failed to get data, retrying\n", e)
                continue

        json1 = response.json()
        print(json1)
        current_time = json1['datetime']
        the_date, the_time = current_time.split('T')
        year, month, mday = [int(x) for x in the_date.split('-')]
        the_time = the_time.split('.')[0]
        hours, minutes, seconds = [int(x) for x in the_time.split(':')]

        # We can also fill in these extra nice things
        year_day = json1['day_of_year']
        week_day = json1['day_of_week']
        is_dst = json1['dst']

        now = time.struct_time(
            (year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst))
        the_rtc.datetime = now
    except Exception as e:
        print('[WARNING]', e)

def attempt_wifi():
    # TODO: Move wifi pass and id to config
    # try connecting to wifi
    print("Connecting to WiFi...")
    try:
        wifi.radio.connect(ssid=secrets['homeSSID'], password=secrets['homePass'])
        #wifi.radio.connect(ssid="Stanford") # open network
        print("Signal: {}".format(wifi.radio.ap_info.rssi))
        # Create a socket pool
        pool = socketpool.SocketPool(wifi.radio)
        # sync out RTC from the web
        synctime(pool)
    except Exception as e:
        print("Unable to connect to WiFi: {}".format(e))
        return None
    else:
        return pool

def get_new_messages():
    '''
    Req: Must be called before radios are initialized, otherwise will fail
    '''
    new_messages = {}
    if alarm.wake_alarm:
        # hacky way of checking the radios without initalizing the hardware
        for r, cs in GS.radios.items(): # This uses a temporary list
            if GS.rx_done(cs):
                print(r, end=": ")
                for msg in GS.get_msg2(cs):
                    if msg is not None:
                        print("[{}] rssi:{}".format(bytes(msg), GS.last_rssi), end=", ")
                        if (msg == b'CRC ERROR'):
                            print("Failed crc check")
                            continue
                        else:
                            # radio, time, gs id, msg, rssi, new?
                            new_messages[r] = {
                                "Radio": r,
                                "Time": time.time(),
                                "ID": ID,
                                "Hexlify MSG": hexlify(msg),
                                "Bytes MSG": str(bytes(msg)),
                                "RSSI": GS.last_rssi,
                                "N": 1,
                            }
                            print(new_messages[r])
                            print("passes crc check")
                print()
        print("Done checking")
        radios = GS.init_radios(SAT)
        return new_messages

def set_up_mqtt(pool):
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
        "ID": GS.id,
        "#": GS.counter,
        "MSG#": GS.msg_count,
        "MSG_Cache": GS.msg_cache,
        "Battery": GS.battery_voltage,
        "WiFi_RSSI": wifi.radio.ap_info.rssi,
    }

    mqtt_client.connect()
    mqtt_client.subscribe(REMOTE_TOPIC)
    
    print("Sending status")
    message = "GS {} status: ".format(ID) + json.dumps(status)
    mqtt_client.publish(STATUS_TOPIC, message)

    GS.mqtt_client = mqtt_client

def send_cache_messages():
    if GS.msg_cache:
            with open("/data.txt", "r") as f:
                l = f.readline()
                while l:
                    message = "Sending cached message: " + l.strip()
                    GS.mqtt_client.publish(DATA_TOPIC, message)
                    l = f.readline()
            try:
                os.remove("/data.txt")
            except:
                pass
            GS.msg_cache = 0

def check_for_commands():
    queuedUp = None
    loopOnce = True
    waitTime = 30
    print("Waiting {} seconds for commands to be sent to ground station before processing".format(waitTime))
    GS.mqtt_client.publish(REMOTE_TOPIC, "Waiting {} seconds for commands to be sent to ground station before processing".format(waitTime))
    time.sleep(waitTime)

    # Loop through commands
    while loopOnce or queuedUp != None:
        loopOnce = False
        try:
            #Grab next command
            queuedUp = GS.mqtt_client.loop()
        except:
            print("Error on mqtt loop")
        else:
            print(queuedUp)
        time.sleep(2)

def main():
    
    GS.id = ID

    # if we haven't slept yet, init radios
    if not alarm.wake_alarm:
        print("First boot")
        GS.init_radios(SAT)
        # reset counters
        GS.counter = 0
        GS.msg_count = 0
        GS.msg_cache = 0
        GS.deep_sleep = 600
    else:
        # Temporary radio list
        # TODO move this to _init_ in GS class, and make sure its not hard coded
        GS.radios = {1: GS.R1_CS, 2: GS.R2_CS, 3: GS.R3_CS}


    print(
        "Loop: {}, Total Msgs: {}, Msgs in Cache: {}, Vbatt: {:.1f}".format(
            GS.counter, GS.msg_count, GS.msg_cache, GS.battery_voltage
        )
    )

    # try connecting to wifi
    pool = attempt_wifi()

    # check radios (And initializes them)
    new_messages = get_new_messages()

    if new_messages:
        GS.msg_count = GS.msg_count + 1

    # if we have wifi, connect to mqtt broker
    if wifi.radio.ap_info is not None:
        # try:1069855917

        # Set up a MiniMQTT Client
        set_up_mqtt(pool)

        # send any cached messages
        send_cache_messages()

        # send any new messages
        if new_messages:
            for msg in new_messages:
                print("Sending message")
                print(new_messages[msg])
                #mqtt_client.publish(DATA_TOPIC, new_messages[msg])
                message = "Message received: " + json.dumps(new_messages[msg])
                GS.mqtt_client.publish(DATA_TOPIC, message)

        # check for mqtt remote messages
        check_for_commands()

        GS.mqtt_client.disconnect()

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
            GS.msg_cache = GS.msg_cache + 1

    GS.counter = GS.counter + 1
    GS.gs_listen()
    print("Finished. Deep sleep until RX interrupt or {}s timeout...".format(GS.deep_sleep))
    # wake up on IRQ or after deep sleep time
    # TODO: Make this actually loop through radios so its not a hard 3. Moreover, set the pin number to be set with the radios above
    pin_alarm1 = alarm.pin.PinAlarm(pin=board.IO5, value=True, pull=False)  # radio1
    pin_alarm2 = alarm.pin.PinAlarm(pin=board.IO6, value=True, pull=False)  # radio2
    pin_alarm3 = alarm.pin.PinAlarm(pin=board.IO7, value=True, pull=False)  # radio3
    time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + GS.deep_sleep)
    alarm.exit_and_deep_sleep_until_alarms(time_alarm, pin_alarm1, pin_alarm2, pin_alarm3)

if __name__ == '__main__':
    main()
