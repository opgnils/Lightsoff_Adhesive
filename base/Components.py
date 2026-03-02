from collections import namedtuple



ComponentPositions = namedtuple('ComponentPositions', ['coarse', 'intermediate', 'fine', 'target'])

Aruco = namedtuple('Aruco', ['id','position'])

class Component:

    def __init__(self, positions:ComponentPositions, aruco:Aruco):
        self.positions:ComponentPositions = positions
        self.aruco:Aruco = aruco