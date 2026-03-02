"""
Plot Manager for handling matplotlib visualization windows and animations.

Manages multiple plot windows with real-time updates using matplotlib's FuncAnimation.
Provides a clean interface for opening/closing plots and registering plot functions
that follow the required update function structure for animation.
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation

class PlotManager:
    """
    Manages matplotlib plot windows and animated plots for real-time data visualization.

    This class handles the lifecycle of plot windows, manages matplotlib animations,
    and provides a clean interface for registering and controlling multiple plot types.
    It uses threading internally through matplotlib's animation framework.
    """

    def __init__(self, data_collector):
        """
        Initialize the plot manager with a data collector.

        Args:
            data_collector: Object that provides data for plotting (typically UDPServer)
        """
        self.data_collector = data_collector
        self.active_plots = {}  # Stores active plot windows: {plot_name: {'fig': fig, 'ani': ani}}
        self.plot_functions = {}  # Stores registered plot functions: {plot_name: plot_func}
        matplotlib.use('TkAgg')  # Use TkAgg backend for thread-safe plotting

    def add_plot_function(self, plot_name, plot_func):
        """
        Register a plot function for creating a specific type of plot.

        Args:
            plot_name: String identifier for the plot type (e.g., 'aruco', 'holes')
            plot_func: Function that creates the plot layout and returns update function
        """
        self.plot_functions[plot_name] = plot_func

    def open_plot(self, plot_name):
        """
        Open a new plot window using the registered plot function.

        Creates a matplotlib figure, calls the registered plot function to set up
        the layout and get the update function, then starts the animation loop.

        Args:
            plot_name: Name of the registered plot function to use
        """
        if plot_name not in self.plot_functions:
            print(f"WARNING No plot function registered for '{plot_name}'")
            return

        try:
            # Create figure with subplots (most plots use 2x1 layout)
            fig, axs = plt.subplots(2, 1, figsize=(10, 12))
            update_func = self.plot_functions[plot_name](fig, axs, self.data_collector)

            # Create animation with 50ms interval (20 FPS)
            ani = animation.FuncAnimation(
                fig, update_func, interval=50, cache_frame_data=False
            )

            self.active_plots[plot_name] = {'fig': fig, 'ani': ani}

            # Register close event handler to clean up when window is closed
            def on_close(event):
                self.close_plot(plot_name)

            fig.canvas.mpl_connect('close_event', on_close)
            plt.show(block=False)  # Non-blocking show
            print(f"{plot_name.upper()} plot window opened")

        except Exception as e:
            print(f"Error opening {plot_name} plot: {e}")

    def close_plot(self, plot_name):
        """
        Close the plot window for the given plot name.

        Stops the animation and closes the matplotlib figure.

        Args:
            plot_name: Name of the plot to close
        """
        if plot_name in self.active_plots:
            plt.close(self.active_plots[plot_name]['fig'])
            print(f"{plot_name.upper()} plot window closed")
        else:
            print(f"No active plot window for {plot_name}")

if __name__ == "__main__":
    """
    Test/demo code for the PlotManager with fake data.

    Creates a fake data collector that generates sine wave data and demonstrates
    the plot manager functionality with a simple animated plot.
    """
    import numpy as np
    import time
    import threading

    class FakeDataCollector:
        """Fake data collector for testing the plot manager."""
        def __init__(self):
            self.x = []
            self.y = []
            self.lock = threading.Lock()
            self.running = True
            self.t = 0
            # Start background thread to generate data
            threading.Thread(target=self._update, daemon=True).start()

        def _update(self):
            """Background thread that continuously generates sine wave data."""
            while self.running:
                with self.lock:
                    self.x.append(self.t)
                    self.y.append(np.sin(self.t))
                    if len(self.x) > 200:  # Keep only last 200 points
                        self.x.pop(0)
                        self.y.pop(0)
                    self.t += 0.1
                time.sleep(0.05)

        def get_current_data(self):
            """Thread-safe access to current data."""
            with self.lock:
                return self.x.copy(), self.y.copy()

        def stop(self):
            """Stop the data generation thread."""
            self.running = False

    def simple_plot(fig, axs, data_collector):
        """
        Example plot function that creates a simple animated sine wave plot.

        This demonstrates the required structure for plot functions:
        1. Set up the plot layout and initial empty plot elements
        2. Return an update function that takes a frame number and returns plot elements

        Args:
            fig: Matplotlib figure
            axs: Array of subplot axes
            data_collector: Data source object

        Returns:
            update_func: Function called by FuncAnimation for each frame
        """
        ax = axs[0]
        ax.set_title('Live Sine Wave')
        ax.set_xlabel('Time')
        ax.set_ylabel('Value')
        line, = ax.plot([], [], 'b-')  # Empty line to be updated

        # Second subplot for the histogram
        ax_hist = axs[1]
        ax_hist.set_title('Value Histogram')
        ax_hist.set_xlabel('Value')
        ax_hist.set_ylabel('Frequency')
        hist, = ax_hist.plot([], [], 'r-')

        def update(frame):
            """
            Update function called by FuncAnimation for each frame.

            Args:
                frame: Frame number (provided by matplotlib)

            Returns:
                Tuple of plot elements that were updated (for blitting optimization)
            """
            x, y = data_collector.get_current_data()
            line.set_data(x, y)

            # Update histogram
            ax_hist.clear()
            ax_hist.set_title('Value Histogram')
            ax_hist.set_xlabel('Value')
            ax_hist.set_ylabel('Frequency')
            ax_hist.hist(y, bins=20, color='red', alpha=0.7)

            ax.relim()
            ax.autoscale_view()
            return line, hist,

        return update

    # Demo the plot manager with fake data
    collector = FakeDataCollector()
    manager = PlotManager(collector)
    manager.add_plot_function('sine', simple_plot)
    manager.open_plot('sine')
    print("Plot will be open for 5 seconds...")

    start_time = time.time()
    try:
        while time.time() - start_time < 5:
            plt.pause(0.1)  # Allow matplotlib to process events
        if 'sine' in manager.active_plots:
            manager.close_plot('sine')
    except KeyboardInterrupt:
        collector.stop()
        print("\nStopped.")
    collector.stop()
    print("Done.")