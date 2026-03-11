# Phase 6 Implementation Guide

This document provides a comprehensive overview of the implementation process for Phase 6 of the PDF Manager project. It covers the save endpoint, export functionality for PDF, CSV, XLSX, and JSON formats, along with the database models for `FieldEditHistory` and `AuditLog`, Flask route implementations, and testing examples.

## 1. Save Endpoint

### Endpoint Definition
- **URL**: `/api/save`
- **Method**: `POST`

### Request Body
```json
{
  "data": { ... },
  "format": "pdf"  
}
```
- `data`: The content to be saved.
- `format`: The format of the file to be saved (PDF, CSV, XLSX, JSON).

### Response
- **Status**: 200 OK
- **Body**: A message confirming save success.

### Example Implementation
```python
@app.route('/api/save', methods=['POST'])
def save_data():
    content = request.json['data']
    format = request.json['format']
    # Implement save logic here
    return jsonify({'message': 'Data saved successfully'}), 200
```

## 2. Export Functionality

### Supported Formats
- **PDF**: Generates a PDF document from the provided data.
- **CSV**: Creates a CSV file.
- **XLSX**: Generates an Excel file.
- **JSON**: Outputs data in JSON format.

### Example Implementation
```python
@app.route('/api/export/<string:format>', methods=['GET'])
def export_data(format):
    # Implement the logic for exporting data in the desired format
    return send_file(exported_file_path)
```

## 3. Database Models
### 3.1 FieldEditHistory
```python
class FieldEditHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(100))
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
```

### 3.2 AuditLog
```python
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100))
    user_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
```

## 4. Testing Examples
### Save Endpoint Test
```python
class SaveEndpointTestCase(unittest.TestCase):
    def test_save_success(self):
        response = self.app.post('/api/save', json={'data': {...}, 'format': 'pdf'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Data saved successfully', response.get_data(as_text=True))
```

### Export Functionality Test
```python
class ExportEndpointTestCase(unittest.TestCase):
    def test_export_to_csv(self):
        response = self.app.get('/api/export/csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/csv')
```

## Conclusion
This guide provides the necessary information to implement the features in Phase 6 successfully. Ensure you follow best practices and test all functionalities thoroughly.