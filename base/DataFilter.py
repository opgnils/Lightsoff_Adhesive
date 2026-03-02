"""
Data filtering system using pandas for time series processing.

Provides real-time data filtering, outlier detection, resampling, and smoothing for distributed
cambot data streams. Uses pandas DataFrames for efficient time series operations and TTL caching
for memory management. Integrates with UDPServer for processing incoming sensor data.
"""

# Refactored DataFilter using pandas for time series filtering, resampling, and outlier detection
import pandas as pd
import numpy as np
import time
from cachetools import TTLCache

class DataFilter:
    """
    Real-time data filtering and processing system for distributed cambot data.

    Manages multiple data streams with pandas DataFrames, performs outlier detection based on
    delta thresholds, and provides resampling and smoothing capabilities. Uses TTL caching
    to automatically clean up old data and prevent memory leaks.
    """

    def __init__(self, max_history=100, ttl=10):
        """
        Initialize the data filter with caching and storage structures.

        Args:
            max_history: Maximum number of data points to keep per stream
            ttl: Time-to-live in seconds for message cache
        """
        # Structure: {(tag, cambot_id, *keys): pandas.DataFrame}
        self.data_streams = {}  # Stores time series data as pandas DataFrames
        self.filter_configs = {}  # Stores filter configurations
        self.max_history = max_history  # Maximum history per data stream
        self.ttl = ttl  # TTL for message cache
        self.message_cache = TTLCache(maxsize=1000, ttl=ttl)  # Cache for raw messages

    def clear(self):
        """Clear all data streams, filter configs, and message cache."""
        self.data_streams.clear()
        self.filter_configs.clear()
        self.message_cache.clear()

    def add_filter(self, tag, cambot_id, keys, delta_threshold=None):
        """
        Register a data stream to be filtered and processed.

        Args:
            tag: Message tag (e.g., 'aruco', 'holes')
            cambot_id: Specific cambot ID or None for all cambots
            keys: Tuple of keys to extract values from messages
            delta_threshold: Threshold for outlier detection (absolute change)
        """
        filter_key = (tag, cambot_id, *keys)
        self.filter_configs[filter_key] = {
            'delta_threshold': delta_threshold
        }
        # Initialize empty DataFrame with timestamp index
        if filter_key not in self.data_streams:
            self.data_streams[filter_key] = pd.DataFrame(
                columns=['value', 'is_outlier'],
                index=pd.DatetimeIndex([])
            )

    def process_message(self, message):
        """
        Process an incoming message through all registered filters.

        Extracts values using configured keys, performs outlier detection,
        and stores data in pandas DataFrames with timestamps.

        Args:
            message: Incoming message dict from cambot
        """
        tag = message.get('tag')
        cambot_id = message.get('cambot_id')
        timestamp = message.get('time', time.time())
        # Store raw message for debugging
        self.message_cache[timestamp] = message

        # Process for each registered filter
        for filter_key, config in self.filter_configs.items():
            # Check if tag matches and cambot_id matches (None means match all)
            if (filter_key[0] == tag and
                (filter_key[1] is None or filter_key[1] == cambot_id)):
                # Extract value using the keys
                keys = filter_key[2:]
                value = self._extract_value(message, keys)
                if value is not None:
                    # For wildcard filters (None cambot_id), create specific stream
                    actual_key = (tag, cambot_id, *keys) if filter_key[1] is None else filter_key

                    # Initialize stream if needed
                    if actual_key not in self.data_streams:
                        self.data_streams[actual_key] = pd.DataFrame(
                            columns=['value', 'is_outlier'],
                            index=pd.DatetimeIndex([])
                        )

                    # Convert to scalar if it's a simple array
                    if isinstance(value, np.ndarray) and value.size == 1:
                        value = float(value)
                    is_outlier = self._is_outlier(
                        actual_key, value,
                        delta_threshold=config.get('delta_threshold')
                    )
                    df = self.data_streams[actual_key]
                    new_row = pd.DataFrame(
                        {'value': [value], 'is_outlier': [is_outlier]},
                        index=[pd.Timestamp(timestamp, unit='s')]
                    )
                    # Handle concatenation properly to avoid FutureWarning
                    if df.empty:
                        self.data_streams[actual_key] = new_row.iloc[-self.max_history:]
                    else:
                        self.data_streams[actual_key] = pd.concat([df, new_row], ignore_index=False).iloc[-self.max_history:]

    def _extract_value(self, message, keys):
        """
        Extract nested value from message using key path.

        Args:
            message: Message dictionary
            keys: Tuple of keys for nested access

        Returns:
            Extracted value or None if path doesn't exist
        """
        try:
            value = message
            for key in keys:
                value = value[key]
            return np.array(value) if not isinstance(value, np.ndarray) else value
        except (KeyError, TypeError, IndexError):
            return None

    def _is_outlier(self, filter_key, value, delta_threshold=None):
        """
        Detect if a value is an outlier based on delta threshold.

        Compares current value to last valid (non-outlier) value and flags
        if the absolute change exceeds the threshold.

        Args:
            filter_key: Stream identifier
            value: Current value to check
            delta_threshold: Threshold for outlier detection

        Returns:
            True if value is an outlier, False otherwise
        """
        df = self.data_streams[filter_key]
        if len(df) < 2 or df[~df['is_outlier']].empty:
            return False
        last_valid = df[~df['is_outlier']]['value'].iloc[-1]
        if np.isscalar(value) and np.isscalar(last_valid):
            delta = abs(value - last_valid)
            return delta_threshold is not None and delta > delta_threshold
        elif isinstance(value, np.ndarray) and isinstance(last_valid, np.ndarray):
            delta = np.linalg.norm(value - last_valid)
            return delta_threshold is not None and delta > delta_threshold
        return False

    def get_data(self, tag, cambot_id, keys, num_points=10, include_outliers=False):
        """
        Retrieve filtered data from a specific stream.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            num_points: Number of recent points to return
            include_outliers: Whether to include flagged outliers

        Returns:
            Pandas DataFrame with time series data or None if not found
        """
        filter_key = (tag, cambot_id, *keys)
        if filter_key not in self.data_streams:
            return None
        df = self.data_streams[filter_key]
        if df.empty:
            return None

        # Check if required columns exist
        if 'value' not in df.columns or 'is_outlier' not in df.columns:
            return None

        if include_outliers:
            result = df
        else:
            result = df[~df['is_outlier']]
        if len(result) == 0:
            return None
        return result.iloc[-num_points:] if num_points < len(result) else result

    def get_resampled_data(self, tag, cambot_id, keys, freq='100ms'):
        """
        Get data resampled to regular time intervals.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            freq: Resampling frequency (e.g., '100ms' = 10Hz)

        Returns:
            Pandas DataFrame with resampled data or None
        """
        data = self.get_data(tag, cambot_id, keys, include_outliers=False)
        if data is None or len(data) < 2:
            return None

        # Check if we're dealing with scalar or vector data
        sample_value = data['value'].iloc[0]

        if np.isscalar(sample_value) or (isinstance(sample_value, np.ndarray) and sample_value.size == 1):
            # For scalar data, use pandas resample directly
            return data[['value']].resample(freq).mean()
        else:
            # For vector data, we need custom resampling
            # For now, just return the original data as resampling vector data is complex
            # This could be enhanced later if needed
            return data[['value']]

    def get_smoothed_data(self, tag, cambot_id, keys, window=5):
        """
        Get smoothed data using rolling window averaging.

        Args:
            tag: Message tag
            cambot_id: Cambot ID
            keys: Data extraction keys
            window: Rolling window size for smoothing

        Returns:
            Pandas DataFrame with smoothed data or None
        """
        data = self.get_data(tag, cambot_id, keys, include_outliers=False)
        if data is None or len(data) < window:
            return None

        # Check if we're dealing with scalar or vector data
        sample_value = data['value'].iloc[0]

        if np.isscalar(sample_value) or (isinstance(sample_value, np.ndarray) and sample_value.size == 1):
            # For scalar data, use pandas rolling mean directly
            smoothed = data[['value']].rolling(window=window, min_periods=1).mean()
            # Add back the is_outlier column as False for all smoothed data
            smoothed['is_outlier'] = False
            return smoothed
        else:
            # For vector data (numpy arrays), we need to handle each component separately
            smoothed_values = []
            timestamps = data.index.tolist()

            # Convert values to a proper numpy array
            value_arrays = np.array([np.array(val) for val in data['value'].values])

            # Apply rolling window to each component
            for i in range(len(data)):
                start_idx = max(0, i - window + 1)
                end_idx = i + 1
                window_data = value_arrays[start_idx:end_idx]

                # Compute mean across the window
                smoothed_val = np.mean(window_data, axis=0)
                smoothed_values.append(smoothed_val)

            # Create new DataFrame with smoothed values
            smoothed_df = pd.DataFrame(
                {
                    'value': smoothed_values,
                    'is_outlier': [False] * len(smoothed_values)
                },
                index=timestamps
            )
            return smoothed_df