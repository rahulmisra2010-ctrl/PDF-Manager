# JavaScript SDK

A lightweight JavaScript/TypeScript client for the PDF Manager API. Works in both **Node.js** and **browser** environments.

## Installation

The SDK is not yet published to npm. Copy the class below into your project.

```bash
# Future installation (planned)
npm install pdf-manager-sdk
```

---

## Quick Start

```javascript
const { PDFManagerClient } = require('./pdf-manager-sdk');

const client = new PDFManagerClient({
  baseUrl: 'http://localhost:5000',
  username: 'admin',
  password: 'yourpassword',
});

await client.login();

// Upload
const { document_id } = await client.upload('invoice.pdf');

// Extract
const { fields } = await client.extractAI(document_id);
fields.forEach(f => console.log(f.field_name, f.value));

// Update a field
await client.updateField(fields[0].id, 'corrected value');

// Clean up
await client.deleteDocument(document_id);
```

---

## SDK Source

Save this as `pdf-manager-sdk.js` in your project:

```javascript
'use strict';

/**
 * pdf-manager-sdk.js — JavaScript SDK for the PDF Manager REST API.
 * Compatible with Node.js 18+ and modern browsers.
 */

class PDFManagerClient {
  /**
   * @param {object} options
   * @param {string} [options.baseUrl='http://localhost:5000']
   * @param {string} [options.username]
   * @param {string} [options.password]
   * @param {number} [options.maxRetries=3]
   */
  constructor({ baseUrl = 'http://localhost:5000', username, password, maxRetries = 3 } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.username = username;
    this.password = password;
    this.maxRetries = maxRetries;
    this._cookies = '';
  }

  // -------------------------------------------------------------------------
  // Auth
  // -------------------------------------------------------------------------

  async login(username, password) {
    const u = username ?? this.username;
    const p = password ?? this.password;
    const body = new URLSearchParams({ username: u, password: p });
    const resp = await this._fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    // In Node.js, capture the session cookie manually
    const setCookie = resp.headers.get('set-cookie');
    if (setCookie) this._cookies = setCookie;
    return true;
  }

  async logout() {
    await this._fetch('/auth/logout');
    this._cookies = '';
  }

  // -------------------------------------------------------------------------
  // Documents
  // -------------------------------------------------------------------------

  async upload(filePath) {
    const FormData = globalThis.FormData ?? require('form-data');
    const form = new FormData();

    if (typeof filePath === 'string') {
      // Node.js: stream the file
      const fs = require('fs');
      const path = require('path');
      form.append('file', fs.createReadStream(filePath), path.basename(filePath));
    } else {
      // Browser: File or Blob
      form.append('file', filePath);
    }

    const resp = await this._rawFetch('/api/v1/upload', {
      method: 'POST',
      body: form,
      headers: typeof form.getHeaders === 'function' ? form.getHeaders() : {},
    });
    return this._json(resp);
  }

  async listDocuments({ page = 1, perPage = 20 } = {}) {
    return this._get(`/api/v1/documents?page=${page}&per_page=${perPage}`);
  }

  async getDocument(documentId) {
    return this._get(`/api/v1/documents/${documentId}`);
  }

  async deleteDocument(documentId) {
    return this._request('DELETE', `/api/v1/documents/${documentId}`);
  }

  // -------------------------------------------------------------------------
  // Extraction
  // -------------------------------------------------------------------------

  async extractOCR(documentId) {
    return this._request('POST', `/api/v1/extract/ocr/${documentId}`);
  }

  async extractAI(documentId, { runRag = true, includeImages = false } = {}) {
    return this._request('POST', `/api/v1/extract/ai/${documentId}?include_images=${includeImages}`, {
      body: JSON.stringify({ run_rag: runRag }),
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // -------------------------------------------------------------------------
  // Fields
  // -------------------------------------------------------------------------

  async getFields(documentId) {
    return this._get(`/api/v1/fields/${documentId}`);
  }

  async updateField(fieldId, value) {
    return this._request('PUT', `/api/v1/fields/${fieldId}`, {
      body: JSON.stringify({ value }),
      headers: { 'Content-Type': 'application/json' },
    });
  }

  async getFieldHistory(fieldId) {
    return this._get(`/api/v1/fields/${fieldId}/history`);
  }

  // -------------------------------------------------------------------------
  // Stats & Search
  // -------------------------------------------------------------------------

  async getStats() {
    return this._get('/api/stats');
  }

  async search(query) {
    return this._get(`/search/api?q=${encodeURIComponent(query)}`);
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  _authHeaders() {
    return this._cookies ? { Cookie: this._cookies } : {};
  }

  async _get(path) {
    return this._request('GET', path);
  }

  async _request(method, path, options = {}) {
    const resp = await this._rawFetch(path, { method, ...options });
    return this._json(resp);
  }

  async _rawFetch(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = { ...this._authHeaders(), ...(options.headers ?? {}) };

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      const resp = await fetch(url, { credentials: 'include', ...options, headers });

      if (resp.status === 429) {
        const reset = resp.headers.get('X-RateLimit-Reset');
        const waitMs = reset
          ? Math.max(1000, Number(reset) * 1000 - Date.now())
          : 5000;
        await new Promise(r => setTimeout(r, waitMs));
        continue;
      }

      if (!resp.ok) {
        let error;
        try { error = (await resp.json()).error; } catch { error = resp.statusText; }
        throw new Error(`API ${resp.status}: ${error}`);
      }

      return resp;
    }
    throw new Error('Max retries exceeded');
  }

  async _json(resp) {
    return resp.json();
  }
}

module.exports = { PDFManagerClient };
```

---

## TypeScript Types

```typescript
interface Document {
  id: number;
  filename: string;
  file_path: string;
  status: 'uploaded' | 'extracted' | 'edited' | 'approved' | 'rejected';
  page_count: number | null;
  file_size: number | null;
  uploaded_by: number | null;
  created_at: string;
}

interface ExtractedField {
  id: number;
  document_id: number;
  field_name: string;
  value: string;
  confidence: number;
  is_edited: boolean;
  original_value: string | null;
  version: number;
  bbox_x: number | null;
  bbox_y: number | null;
  bbox_width: number | null;
  bbox_height: number | null;
}

interface FieldHistoryEntry {
  id: number;
  field_id: number;
  old_value: string | null;
  new_value: string;
  edited_by: number | null;
  edited_at: string;
}
```

---

## API Reference

### Constructor Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | string | `http://localhost:5000` | API server URL |
| `username` | string | — | Username for auto-login |
| `password` | string | — | Password for auto-login |
| `maxRetries` | number | `3` | Retry count on 429 |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `login(username?, password?)` | Promise\<boolean\> | Authenticate |
| `logout()` | Promise\<void\> | End session |
| `upload(filePath)` | Promise\<object\> | Upload PDF |
| `listDocuments({ page, perPage })` | Promise\<object\> | List documents |
| `getDocument(id)` | Promise\<Document\> | Get document |
| `deleteDocument(id)` | Promise\<object\> | Delete document |
| `extractOCR(id)` | Promise\<object\> | OCR extraction |
| `extractAI(id, { runRag, includeImages })` | Promise\<object\> | AI extraction |
| `getFields(documentId)` | Promise\<ExtractedField[]\> | Get fields |
| `updateField(fieldId, value)` | Promise\<ExtractedField\> | Update field |
| `getFieldHistory(fieldId)` | Promise\<FieldHistoryEntry[]\> | Field history |
| `getStats()` | Promise\<object\> | Dashboard stats |
| `search(query)` | Promise\<object\> | Search |
