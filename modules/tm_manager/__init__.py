from ...models.fields import FieldSet

class TMManager:
    def __init__(self, ip, APIKey):
        self.ip = ip
        self.APIKey = APIKey

    def connect(self):
        pass

    def query(self, endpoint: str):
        pass

    def send_command(self, command: str, data: dict):
        pass

    def connect_to_field_set(self, field_set: FieldSet):
        pass

    def disconnect_from_field_set(self, field_set: FieldSet):
        pass