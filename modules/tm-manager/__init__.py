class MatchEntity:
    def __init__(self, start_time, field=None, duration=60):
        self.start_time = start_time
        self.duration = duration
        self.field = field