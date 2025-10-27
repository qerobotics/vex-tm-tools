class Field:
    def __init__(self, field_id, name):
        self.field_id = field_id
        self.name = name
    
class FieldSet:
    def __init__(self, field_set_id):
        self.field_set_id = field_set_id

    def get_fields(self):
        pass