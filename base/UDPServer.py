"""
UDP Server for handling distributed cambot communication.

Central hub that receives UDP messages from remote cambots, manages message queues with TTL caching,
integrates with DataFilter for real-time data processing, and provides logging capabilities.
Supports concurrent message handling through threading and maintains active client tracking.
"""

import socket
import threading
from cachetools import TTLCache, Cache
import pickle
import time
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import json
import numpy as np

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.'))
from DataFilter import DataFilter

def make_serializable(obj):
    """
    Convert numpy arrays and complex objects to JSON-serializable format for logging.

    Args:
        obj: Object to make serializable (numpy arrays, dicts, lists)

    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    else:
        return obj

class UDPServer:
    """
    Main UDP server class for distributed cambot communication.

    Handles incoming UDP messages from remote cambots, maintains message queues with TTL,
    integrates data filtering for real-time processing, and provides comprehensive logging.
    Designed for concurrent operation with thread-safe message handling.
    """

    max_cache_size = 100  # Maximum messages per cambot/tag combination

    def __init__(self, host='0.0.0.0', port=12345, ssh_config=r'./ssh/config_lightsoff'):
        """
        Initialize UDP server with networking and data processing components.

        Args:
            host: IP address to bind server to (default: all interfaces)
            port: UDP port to listen on
            ssh_config: Path to SSH configuration file for remote connections
        """
        self.server_address = (host, port)
        self.port = port
        self.ssh_config = ssh_config
        self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_thread = None  # Thread for handling incoming messages
        self.shutting_down = False  # Flag for graceful shutdown
        self.message_queues = {}  # {(cambot_id, tag): TTLCache} for message storage
        self.data_filter = DataFilter(max_history=self.max_cache_size, ttl=10)  # Data filtering component
        self.logger = None  # Rotating file logger

    def start_server(self):
        """
        Start the UDP server and begin listening for incoming messages.

        Binds to the specified address and starts a daemon thread to handle
        incoming UDP packets concurrently with the main application.
        """
        self.udp_server.bind(self.server_address)
        print(f"Server listening on {self.server_address}")

        def handle_requests():
            """
            Main message handling loop running in separate thread.

            Continuously receives UDP packets, unpickles messages, stores them
            in TTL caches, processes through data filter, and logs if enabled.
            """
            while True:
                try:
                    # Receive UDP packet with 1KB buffer
                    data, client_address = self.udp_server.recvfrom(1024)

                    try:
                        # Unpickle the received message
                        message = pickle.loads(data)

                        # Extract message metadata for queue organization
                        cambot_id = message["cambot_id"]
                        tag = message["tag"]
                        key = (cambot_id, tag)

                        # Initialize TTL cache for new cambot/tag combinations
                        if key not in self.message_queues:
                            self.message_queues[key] = TTLCache(maxsize=self.max_cache_size, ttl=10)

                        # Store message with timestamp as key
                        self.message_queues[key][time.time()] = message

                        # Process message through data filter for outlier detection
                        self.data_filter.process_message(message)

                        # Log message if logging is enabled
                        if self.logger:
                            serializable_message = make_serializable(message)
                            self.logger.info(json.dumps(serializable_message))

                    except pickle.UnpicklingError:
                        print("Received data could not be unpickled")

                except:
                    pass  # Continue processing even if individual messages fail

                # Check for shutdown signal
                if self.shutting_down:
                    break

        # Start message handling thread as daemon
        self.recv_thread = threading.Thread(target=handle_requests)
        self.recv_thread.daemon = True
        self.recv_thread.start()

    def start_logging(self, name: str):
        """
        Start JSONL logging to rotating files.

        Args:
            name: Base name for log files (timestamp will be appended)
        """
        if self.logger is not None:
            self.stop_logging()  # Stop any existing logging

        start_time = int(time.time())
        os.makedirs('./logs', exist_ok=True)
        filename = os.path.join('./logs', f"{name}_log_{start_time}.jsonl")

        # Setup rotating file handler (10MB files, 5 backups)
        self.logger = logging.getLogger(f'udp_logger_{name}')
        handler = RotatingFileHandler(filename, maxBytes=10*1024*1024, backupCount=5)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def stop_logging(self):
        """Stop logging and close file handlers."""
        if self.logger:
            for handler in self.logger.handlers:
                handler.close()
            self.logger = None

    def get_active_clients(self) -> list:
        """
        Get list of currently active cambot clients.

        Returns:
            List of unique cambot IDs that have sent messages recently
        """
        return list(set(cambot_id for cambot_id, _ in self.message_queues.keys()))

    def get_message_by_tag(self, tag: str, cambot_ids=None, num=1):
        """
        Retrieve recent messages by tag from specified cambots.

        Args:
            tag: Message tag to filter by
            cambot_ids: List of cambot IDs to query (None = all active)
            num: Number of most recent messages to return per cambot

        Returns:
            Dict of {cambot_id: [messages]} with recent messages
        """
        if cambot_ids is None:
            cambot_ids = self.get_active_clients()

        messages = {}
        for cambot_id in cambot_ids:
            key = (cambot_id, tag)
            if key in self.message_queues:
                # Get most recent 'num' messages
                messages[cambot_id] = list(list(self.message_queues[key].values())[-num:])

        return messages

    def add_filter(self, tag, cambot_id=None, keys=None, delta_threshold=None):
        """
        Add a data filter for real-time outlier detection.

        Args:
            tag: Message tag to filter
            cambot_id: Specific cambot ID (None = all cambots)
            keys: Tuple of keys to extract values from messages
            delta_threshold: Minimum change threshold for outlier detection
        """
        self.data_filter.add_filter(tag, cambot_id, keys, delta_threshold)

    def get_filtered_data(self, tag, cambot_id, keys, num_points=10):
        """
        Get filtered data with outliers removed.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            num_points: Number of recent data points to return

        Returns:
            Pandas DataFrame with filtered time series data
        """
        return self.data_filter.get_data(tag, cambot_id, keys, num_points, include_outliers=False)

    def get_outliers(self, tag, cambot_id, keys, num_points=10):
        """
        Get only the outlier data points.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            num_points: Number of recent outliers to return

        Returns:
            Pandas DataFrame with outlier data points
        """
        data = self.data_filter.get_data(tag, cambot_id, keys, num_points, include_outliers=True)
        if data is not None:
            return data[data['is_outlier']]
        return None

    def get_resampled_data(self, tag, cambot_id, keys, freq='100ms'):
        """
        Get data resampled to regular time intervals.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            freq: Resampling frequency (default: 100ms = 10Hz)

        Returns:
            Pandas DataFrame with resampled data
        """
        return self.data_filter.get_resampled_data(tag, cambot_id, keys, freq)

    def get_smoothed_data(self, tag, cambot_id, keys, window=5):
        """
        Get smoothed data using rolling window averaging.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            window: Rolling window size for smoothing

        Returns:
            Pandas DataFrame with smoothed data
        """
        return self.data_filter.get_smoothed_data(tag, cambot_id, keys, window)

    def close_server(self):
        """
        Gracefully shutdown the UDP server.

        Stops the message handling thread, closes socket, and cleans up logging.
        """
        self.shutting_down = True
        self.recv_thread.join(2)  # Wait up to 2 seconds for thread to finish
        self.udp_server.close()
        if self.logger:
            for handler in self.logger.handlers:
                handler.close()

    def pickle_message_queue(self):
        """
        Create a snapshot of current message queues for debugging/analysis.

        Saves all current message queues to a pickle file with timestamp.
        Useful for post-processing or debugging communication issues.
        """
        snapshot_path = './server_snapshots'
        os.makedirs(snapshot_path, exist_ok=True)

        # Convert TTL caches to regular dicts for pickling
        frozen_qs = {}
        for k, q in self.message_queues.items():
            print(type(q))
            frozen_qs[k] = list(q.items())

        # Save snapshot with timestamp
        with open(os.path.join(snapshot_path, f'server_snapshot_{int(time.time())}.pkl'), 'wb') as f:
            pickle.dump(frozen_qs, f)

    def send_simple_message(self, devices: list, message: str):
        """
        Send a simple command message to multiple devices with redundancy.

        Args:
            devices: List of device dictionaries with HostName
            message: Command message to send (e.g., 'stop', 'start')
        """
        # Create stop packet with timestamp
        stop_packet = {
            'tag': message,
            'time': time.time(),
            'data': {'command': message}
        }
        pickled_message = pickle.dumps(stop_packet)

        # Send to each device multiple times for reliability
        for d in devices:
            addr = (d["HostName"], self.port)
            # Send 50 times with small delays to ensure delivery
            for i in range(50):
                self.udp_server.sendto(pickled_message, addr)
                time.sleep(0.03)
            print(f"Stop message sent 50 times to {d['Host']} at {addr}")

    def clear(self):
        """Clear all message queues and data filters."""
        self.message_queues.clear()
        self.data_filter.clear()