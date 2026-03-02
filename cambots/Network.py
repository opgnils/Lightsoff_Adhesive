import socket
import pickle
import os
import time
import select

class Network:
    
    def __init__(self, server_address:str ='192.168.8.156'):

        # Server address and port        
        self.port = 12345
        self.server_address = (server_address, self.port) 
        self.socket = None
        self.cambot_id = os.getlogin()
    
    def open_socket(self):
        # Create a UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('', self.port))
        
    def close_socket(self):
        # Close the socket
        self.socket.close()

    def send_pickle_packet(self, data:dict, tag = "Default"):
        
        packet = {
            "cambot_id":self.cambot_id,
            'time': time.time(),
            'tag' : tag,
            'data' : data
            }
        dict_packet = pickle.dumps(packet)
        self.socket.sendto(dict_packet, self.server_address)

    def check_for_stop_message(self, timeout=0.01):
        """Check for a UDP message that is simply the string 'stop' (non-blocking)."""
        self.socket.setblocking(True)
        ready = select.select([self.socket], [], [], timeout)
        if ready[0]:
            try:
                data, _ = self.socket.recvfrom(1024)
                msg = pickle.loads(data)
                
                # Check if the unpickled message is a dict with tag='stop'
                if isinstance(msg, dict) and msg.get('tag') == 'stop':
                    print("Received stop command!")
                    return True
                    
            except Exception as e:
                print(f"Error decoding UDP message: {e}")
        
        return False
