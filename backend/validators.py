from wtforms import ValidationError


# Validator for PDF file type
class PDFValidator:
    def __init__(self, message=None):
        self.message = message or 'File must be a PDF.'

    def __call__(self, form, field):
        if not field.data.filename.endswith('.pdf'):
            raise ValidationError(self.message)


# Validator for file size
def file_size(max_size):
    def _file_size(form, field):
        if field.data and len(field.data.read()) > max_size:
            raise ValidationError(f'File size must not exceed {max_size} bytes.')
        field.data.seek(0)  # Reset file pointer
    return _file_size


# Validator for field names
class FieldNameValidator:
    def __init__(self, allowed_names, message=None):
        self.allowed_names = allowed_names
        self.message = message or 'Invalid field name.'

    def __call__(self, form, field):
        if field.data not in self.allowed_names:
            raise ValidationError(self.message)


# Validator for field values
class FieldValueValidator:
    def __init__(self, allowed_values, message=None):
        self.allowed_values = allowed_values
        self.message = message or 'Invalid field value.'

    def __call__(self, form, field):
        if field.data not in self.allowed_values:
            raise ValidationError(self.message)
