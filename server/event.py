from enum_const import EventType

class Event():
    def __init__(self, event_type: EventType):
        self.event_type = event_type