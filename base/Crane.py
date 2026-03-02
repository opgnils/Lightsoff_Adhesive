from collections import namedtuple
import time
from yaspin import yaspin
import numpy as np


class CranePosition:
    def __init__(self, X, Y, Z, A, B, C):
        self._coords = np.array([X, Y, Z, A, B, C], dtype=float)

    @property
    def X(self):
        return self._coords[0]

    @property
    def Y(self):
        return self._coords[1]

    @property
    def Z(self):
        return self._coords[2]

    @property
    def A(self):
        return self._coords[3]

    @property
    def B(self):
        return self._coords[4]

    @property
    def C(self):
        return self._coords[5]

    @property
    def xyzabc(self):
        return self._coords.copy()
    
    def __repr__(self):
        return self.__str__()
    
    def __str__(self):
        return f"X:{self.X}, Y:{self.Y}, Z:{self.Z}, A:{self.A}, B:{self.B}, C:{self.C}"

class Crane:

    def __init__(self):
        pass


    def connect(self):
        with yaspin(text="Connecting to crane...", color="light_green") as spinner:
            #TODO actually do it
            time.sleep(1)
            spinner.ok("✅")
    
    def position_crane(self, pos:CranePosition):
        with yaspin(text=f"Positioning crane at {pos}...", color="light_green") as spinner:
            #TODO actually do it
            time.sleep(1)
            spinner.ok("✅")
            return True
        