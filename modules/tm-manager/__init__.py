class EventEntity:
    def __init__(self, start_time, field=None, duration=None):
        self.start_time = start_time
        self.duration = duration
        self.field = field

class MatchEntity(EventEntity):
    def __init__(self, match_id, start_time, field=None, duration=60):
        super().__init__(start_time=start_time, field=field, duration=duration)
        self.match_id = match_id
