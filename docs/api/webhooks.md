# Webhooks

> **Note:** Webhook delivery is not yet implemented in PDF Manager. This document describes the planned webhook integration.

## Overview

Webhooks allow your application to receive real-time notifications when events occur in PDF Manager, eliminating the need to poll the API.

## Planned Webhook Events

| Event | Description |
|-------|-------------|
| `document.uploaded` | A new PDF was successfully uploaded |
| `document.deleted` | A document was deleted |
| `extraction.completed` | OCR or AI extraction finished |
| `extraction.failed` | Extraction encountered a fatal error |
| `field.updated` | An extracted field value was edited |
| `export.ready` | An export file is ready for download |

## Payload Format

All webhook payloads are JSON with a common envelope:

```json
{
  "event": "extraction.completed",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": {
    "document_id": 42,
    "filename": "invoice.pdf",
    "status": "extracted",
    "field_count": 12
  }
}
```

## Signature Verification

Each webhook request will include an `X-PDF-Manager-Signature` header containing an HMAC-SHA256 signature of the raw request body.

```python
import hmac
import hashlib

def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

```javascript
const crypto = require('crypto');

function verifySignature(secret, payload, signature) {
  const expected = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}
```

## Retry Logic

When a webhook delivery fails (non-2xx response or timeout), PDF Manager will retry with exponential backoff:

| Attempt | Delay |
|---------|-------|
| 1 | Immediate |
| 2 | 5 seconds |
| 3 | 30 seconds |
| 4 | 5 minutes |
| 5 | 30 minutes |

After 5 failed attempts the event is marked as `failed` and no further retries occur.

## Test Endpoints

During development you can use a service like [Webhook.site](https://webhook.site) or [ngrok](https://ngrok.com) to receive webhooks on your local machine.

```bash
# Start ngrok tunnel (example)
ngrok http 5000
# Use the generated URL as your webhook endpoint
```

## Configuring Webhooks

Webhook configuration will be available through the Admin UI or via environment variables:

```env
WEBHOOK_URL=https://your-app.example.com/webhooks/pdf-manager
WEBHOOK_SECRET=your_webhook_secret
```
