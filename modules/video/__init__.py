from ...models.events import EventEntity
from ...models.video import CameraEntity

class VideoModule:
    def __init__(self):
        pass

    def change_camera(self, camera: CameraEntity):
        pass

    def queue_camera_for_event(self, camera: CameraEntity, event: EventEntity):
        pass
    