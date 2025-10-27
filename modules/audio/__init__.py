from ...models.events import EventEntity
from ...models.audio import SongEntity


class AudioModule:
    def __init__(self,keys):
        self.keys = keys

    def queue_song_for_event(self, song: SongEntity, event: EventEntity):
        pass

    def stop_all_sound(self):
        pass