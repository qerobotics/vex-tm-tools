class CameraEntity:
    def __init__(self, camera_id, field, angle):
        self.camera_id = camera_id
        self.field = field
        self.angle = angle

class VideoModule:
    def __init__(self):
        pass

    def change_camera(self, camera: CameraEntity):
        pass