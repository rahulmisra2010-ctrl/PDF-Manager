# JavaScript / Node.js Code Examples

## Prerequisites (Node.js)

```bash
npm install node-fetch form-data
```

> For browser environments, use the native `fetch` API — no additional library is required. For Node.js 18+, `fetch` is available globally.

---

## Authentication

### Browser

```javascript
// Login via POST form submission
async function login(username, password) {
  const body = new URLSearchParams({ username, password });
  const resp = await fetch('http://localhost:5000/auth/login', {
    method: 'POST',
    credentials: 'include',
    body,
  });
  return resp.ok;
}
```

### Node.js

```javascript
const fetch = require('node-fetch');

const BASE_URL = 'http://localhost:5000';
let cookies = '';

async function login(username, password) {
  const body = new URLSearchParams({ username, password });
  const resp = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
    redirect: 'manual',
  });
  // Capture the Set-Cookie header
  cookies = resp.headers.get('set-cookie') || '';
  return true;
}

function authHeaders() {
  return { Cookie: cookies };
}
```

---

## Upload a PDF

### Browser

```javascript
async function uploadPDF(file) {
  const formData = new FormData();
  formData.append('file', file);

  const resp = await fetch(`${BASE_URL}/api/v1/upload`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });
  return resp.json();
}

// Usage with a file input
const fileInput = document.getElementById('pdf-input');
fileInput.addEventListener('change', async () => {
  const result = await uploadPDF(fileInput.files[0]);
  console.log('Document ID:', result.document_id);
});
```

### Node.js

```javascript
const FormData = require('form-data');
const fs = require('fs');

async function uploadPDF(filePath) {
  const form = new FormData();
  form.append('file', fs.createReadStream(filePath));

  const resp = await fetch(`${BASE_URL}/api/v1/upload`, {
    method: 'POST',
    headers: { ...authHeaders(), ...form.getHeaders() },
    body: form,
  });
  return resp.json();
}

const { document_id } = await uploadPDF('/path/to/document.pdf');
```

---

## Extract Data (AI + RAG)

```javascript
async function extractAI(documentId, runRag = true) {
  const resp = await fetch(`${BASE_URL}/api/v1/extract/ai/${documentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    credentials: 'include',
    body: JSON.stringify({ run_rag: runRag }),
  });
  return resp.json();
}

const extraction = await extractAI(document_id);
extraction.fields.forEach(f => {
  console.log(`${f.field_name}: ${f.value} (${(f.confidence * 100).toFixed(0)}%)`);
});
```

---

## List Documents

```javascript
async function listDocuments(page = 1, perPage = 20) {
  const url = new URL(`${BASE_URL}/api/v1/documents`);
  url.searchParams.set('page', page);
  url.searchParams.set('per_page', perPage);

  const resp = await fetch(url.toString(), {
    credentials: 'include',
    headers: authHeaders(),
  });
  return resp.json();
}

const data = await listDocuments();
console.log(`Total: ${data.total} across ${data.pages} pages`);
data.documents.forEach(d => console.log(d.id, d.filename, d.status));
```

---

## Get Extracted Fields

```javascript
async function getFields(documentId) {
  const resp = await fetch(`${BASE_URL}/api/v1/fields/${documentId}`, {
    credentials: 'include',
    headers: authHeaders(),
  });
  return resp.json();
}

const fields = await getFields(document_id);
fields.forEach(f => console.log(`${f.field_name}: ${f.value}`));
```

---

## Update a Field

```javascript
async function updateField(fieldId, newValue) {
  const resp = await fetch(`${BASE_URL}/api/v1/fields/${fieldId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    credentials: 'include',
    body: JSON.stringify({ value: newValue }),
  });
  return resp.json();
}

const updated = await updateField(1, 'Jane Doe');
console.log('Updated:', updated.value, '(version', updated.version, ')');
```

---

## Get Field History

```javascript
async function getFieldHistory(fieldId) {
  const resp = await fetch(`${BASE_URL}/api/v1/fields/${fieldId}/history`, {
    credentials: 'include',
    headers: authHeaders(),
  });
  return resp.json();
}

const history = await getFieldHistory(1);
history.forEach(h => {
  console.log(`${h.edited_at}: '${h.old_value}' → '${h.new_value}'`);
});
```

---

## Delete a Document

```javascript
async function deleteDocument(documentId) {
  const resp = await fetch(`${BASE_URL}/api/v1/documents/${documentId}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: authHeaders(),
  });
  return resp.json();
}

const result = await deleteDocument(document_id);
console.log(result.status); // "deleted"
```

---

## Complete Workflow

```javascript
const BASE_URL = 'http://localhost:5000';

async function processInvoice(filePath) {
  // 1. Upload
  const form = new FormData();
  form.append('file', fs.createReadStream(filePath));
  const { document_id } = await (
    await fetch(`${BASE_URL}/api/v1/upload`, {
      method: 'POST',
      body: form,
      headers: { ...authHeaders(), ...form.getHeaders() },
    })
  ).json();

  // 2. Extract
  const { fields } = await extractAI(document_id);

  // 3. Build export object
  const exported = Object.fromEntries(
    fields.map(f => [f.field_name, f.value])
  );

  console.log('Extracted fields:', exported);
  return exported;
}
```

---

## Error Handling

```javascript
async function apiRequest(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    const resp = await fetch(url, {
      credentials: 'include',
      headers: authHeaders(),
      ...options,
    });

    if (resp.status === 429) {
      const reset = resp.headers.get('X-RateLimit-Reset');
      const waitMs = reset
        ? Math.max(1000, Number(reset) * 1000 - Date.now())
        : 5000;
      console.log(`Rate limited. Retrying in ${waitMs}ms…`);
      await new Promise(r => setTimeout(r, waitMs));
      continue;
    }

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(`API ${resp.status}: ${body.error || resp.statusText}`);
    }

    return resp;
  }
  throw new Error('Max retries exceeded');
}
```
