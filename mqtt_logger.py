import paho.mqtt.client as mqtt
import os
import json
import sys
from datetime import datetime

# Callback when the client receives a message from the server.

def on_message(client, userdata, msg):
    try:
        # Decode the message payload
        message = msg.payload.decode('utf-8')
        
        # Parse the message as JSON
        data = json.loads(message)
        
        # Extract the "after" node if it exists
        after_data = data.get('after', None)
        
        if after_data is not None:
            # Convert the "after" node to a string for logging
            after_str = json.dumps(after_data)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Append the "after" node to the log file
            with open(userdata['logfile'], 'a') as log_file:
                log_file.write(f"[{timestamp}] {msg.topic}: {after_str}\n")
                log_file.flush()
            
            # Print to the console for immediate feedback
            print(f"Received message from topic {msg.topic}: {after_str}")
        else:
            print(f"No 'after' node in the received message from topic {msg.topic}")
    
    except json.JSONDecodeError:
        print(f"Failed to decode message as JSON from topic {msg.topic}: {message}")
    sys.stdout.flush()

# Function to connect to the broker and subscribe to the topic
def mqtt_subscribe(broker, port, topic, logfile):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={'logfile': logfile})
    client.on_message = on_message

    print(f"Connecting to broker {broker}:{port}")
    client.connect(broker, port, 60)
    
    print(f"Subscribing to topic {topic}")
    client.subscribe(topic)
    
    # Blocking call that processes network traffic, dispatches callbacks, and handles reconnecting.
    client.loop_forever()

# Main function
def main():
    broker = os.getenv('MQTT_BROKER', 'localhost')
    port = int(os.getenv('MQTT_PORT', 1883))
    topic = os.getenv('MQTT_TOPIC', '#')
    logfile = os.getenv('LOG_FILE', 'mqtt_logs.txt')

    mqtt_subscribe(broker, port, topic, logfile)

if __name__ == '__main__':
    main()
