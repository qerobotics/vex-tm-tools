class LightEntity:
    def __init__(self):
        self.light_id = light_id
        self.state = state
    
    def turn_on(self):
        self.state = 1

    def turn_off(self):
        self.state = 0

    def set_brightness(self, brightness):
        self.state = brightness/100
    
    def set_pan_tilt(self, pan, tilt):
        self.pan = pan
        self.tilt = tilt
    
    def set_color(self, color):
        self.color = color

class VFXModule:
    def __init__(self, ip):
        self.ip = ip
    
    def preset(self, preset_id):
        pass

    def control_light(self, light: LightEntity):
        pass