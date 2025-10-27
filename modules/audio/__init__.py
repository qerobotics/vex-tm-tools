class SongEntity:
    def __init__(self, id, start_time = 0):
        self.id = id
        self.start_time = start_time

class AudioModule:
    def __init__(self,keys):
        self.keys = keys

    def queue_song_for_match(self, song: SongEntity):
        pass

    def stop_all_sound(self):
        pass
    
    def background_service(self):
        pass