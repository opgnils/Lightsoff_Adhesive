import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..//..')))
from base.UDPServer import UDPServer
import time
import threading
from pynput.keyboard import Key, Listener, KeyCode

server = UDPServer()
server.start_server()

running = True

def on_press(key):
    global running
    if key == KeyCode.from_char('q'):
        running = False
        return False

listener = Listener(on_press=on_press)
listener.start()


while True:   

    aruco_messages = server.get_message_by_tag(tag='aruco', num = -1)    
    for cambot_id, messages in aruco_messages.items():
        for message in messages:
            for aruco_id, aruco_data in message['data'].items():
                print(f"{cambot_id} : Aruco Id: {aruco_id} Distance: {aruco_data['distance']} meters")
                pass

    
    hole_messages = server.get_message_by_tag(tag='holes')
    for cambot_id, messages in hole_messages.items():
        if messages[0]:
            print(f"{cambot_id} detected holes: {list(messages[0]['data'].keys())}")
        else: 
            print("no messages")

    time.sleep(0.1)  # Sleep for 1 second to avoid busy-waiting

    # In the while loop, at the placeholder:
    if not running:
        break

server.close_server()
