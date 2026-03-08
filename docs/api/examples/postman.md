# Postman Collection Setup

## Importing the Collection

### Option 1: Manual Setup

1. Open Postman
2. Click **New → Collection**
3. Name it `PDF Manager API`
4. Add a **Variable** `base_url` with value `http://localhost:5000`

### Option 2: Import JSON

Create a file named `PDF_Manager.postman_collection.json` with the content below, then import it via **File → Import** in Postman.

```json
{
  "info": {
    "name": "PDF Manager API",
    "description": "Complete PDF Manager API collection",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "base_url", "value": "http://localhost:5000" }
  ],
  "item": [
    {
      "name": "Auth",
      "item": [
        {
          "name": "Login",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/auth/login",
            "body": {
              "mode": "urlencoded",
              "urlencoded": [
                { "key": "username", "value": "admin" },
                { "key": "password", "value": "yourpassword" }
              ]
            }
          }
        },
        {
          "name": "Logout",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/auth/logout"
          }
        }
      ]
    },
    {
      "name": "Documents",
      "item": [
        {
          "name": "Upload PDF",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/upload",
            "body": {
              "mode": "formdata",
              "formdata": [
                { "key": "file", "type": "file", "src": "" }
              ]
            }
          }
        },
        {
          "name": "List Documents",
          "request": {
            "method": "GET",
            "url": {
              "raw": "{{base_url}}/api/v1/documents",
              "query": [
                { "key": "page", "value": "1" },
                { "key": "per_page", "value": "20" }
              ]
            }
          }
        },
        {
          "name": "Get Document",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/v1/documents/{{document_id}}"
          }
        },
        {
          "name": "Delete Document",
          "request": {
            "method": "DELETE",
            "url": "{{base_url}}/api/v1/documents/{{document_id}}"
          }
        }
      ]
    },
    {
      "name": "Extraction",
      "item": [
        {
          "name": "OCR Extraction",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/extract/ocr/{{document_id}}"
          }
        },
        {
          "name": "AI Extraction",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/extract/ai/{{document_id}}",
            "header": [{ "key": "Content-Type", "value": "application/json" }],
            "body": {
              "mode": "raw",
              "raw": "{\"run_rag\": true}"
            }
          }
        }
      ]
    },
    {
      "name": "Fields",
      "item": [
        {
          "name": "Get Fields",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/v1/fields/{{document_id}}"
          }
        },
        {
          "name": "Update Field",
          "request": {
            "method": "PUT",
            "url": "{{base_url}}/api/v1/fields/{{field_id}}",
            "header": [{ "key": "Content-Type", "value": "application/json" }],
            "body": {
              "mode": "raw",
              "raw": "{\"value\": \"new value\"}"
            }
          }
        },
        {
          "name": "Field History",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/v1/fields/{{field_id}}/history"
          }
        }
      ]
    },
    {
      "name": "Stats & Search",
      "item": [
        {
          "name": "Dashboard Stats",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/stats"
          }
        },
        {
          "name": "Search",
          "request": {
            "method": "GET",
            "url": {
              "raw": "{{base_url}}/search/api",
              "query": [{ "key": "q", "value": "invoice" }]
            }
          }
        }
      ]
    }
  ]
}
```

---

## Environment Variables

Create a Postman environment with these variables:

| Variable | Initial Value | Description |
|----------|---------------|-------------|
| `base_url` | `http://localhost:5000` | API base URL |
| `document_id` | — | Set after uploading a document |
| `field_id` | — | Set after listing fields |

---

## Pre-request Script (Authentication)

Add this script to the collection's **Pre-request Script** tab to automatically log in if the session has expired:

```javascript
// Auto-login if no session cookie is set
const sessionCookie = pm.cookies.get('session');
if (!sessionCookie) {
  pm.sendRequest({
    url: pm.environment.get('base_url') + '/auth/login',
    method: 'POST',
    header: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: {
      mode: 'urlencoded',
      urlencoded: [
        { key: 'username', value: pm.environment.get('username') },
        { key: 'password', value: pm.environment.get('password') }
      ]
    }
  }, (err, response) => {
    if (err) console.error('Login failed:', err);
    else console.log('Logged in successfully');
  });
}
```

---

## Tests

Add these to request **Tests** tabs for validation:

### Upload PDF

```javascript
pm.test("Status is 201", () => pm.response.to.have.status(201));
pm.test("Response has document_id", () => {
  const json = pm.response.json();
  pm.expect(json).to.have.property('document_id');
  pm.environment.set('document_id', json.document_id);
});
```

### Get Fields

```javascript
pm.test("Status is 200", () => pm.response.to.have.status(200));
pm.test("Response is array", () => {
  pm.expect(pm.response.json()).to.be.an('array');
});
pm.test("Save first field_id", () => {
  const fields = pm.response.json();
  if (fields.length > 0) {
    pm.environment.set('field_id', fields[0].id);
  }
});
```
