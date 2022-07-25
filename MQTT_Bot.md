## Telegram MQTT Bot

We use MQTT for comunication between the ground stations and ourselves. Our ground station receives a signal from our satellite, which then sends 
the data to the MQTT server. Then our bot listens to the MQTT server and sends a message to whoever is using the bot on Telegram.

### Broker:
This is the MQTT broker link. <br>
Host: broker.mqttdashboard.com <br>
Port: 1883 <br>
Link: tcp://broker.mqttdashboard.com:1883 <br>

### Web Client:
We can also use HiveHQ to access a web client to connect to the Mqtt server with http://www.hivemq.com/demos/websocket-client/ <br>
This lets us actively view the subscriptions.

### Telegram:
This messaging app allows for us to commincate with our bot and for the bot to send us messages.<br>
The bot name is under: gsStanfordBot

Heroku is the online hosting service that is hosting our bot. The bot name under Heroku (also known as an app) is gsstanfordbot. 
The bot is connected to my account for free hosting. Contact agamarra@stanford.edu for info on this.

Followed this guide under Heroku to set up the bot: 
https://github.com/xDWart/mqtg-bot


