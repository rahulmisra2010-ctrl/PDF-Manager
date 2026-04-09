# Cloud Platform Deployment

See the [Installation – Cloud](../installation/cloud.md) page for step-by-step instructions for AWS ECS, Google Cloud Run, and Azure Container Apps.

## Quick Links

- [AWS ECS Deployment](../installation/cloud.md#aws-elastic-container-service-ecs)
- [Google Cloud Run](../installation/cloud.md#google-cloud-platform-cloud-run)
- [Azure Container Apps](../installation/cloud.md#azure-container-apps)

## Additional Considerations for Production

### Managed Databases

Use a managed PostgreSQL service in your cloud of choice:

| Cloud | Service |
|-------|---------|
| AWS | Amazon RDS for PostgreSQL |
| GCP | Cloud SQL for PostgreSQL |
| Azure | Azure Database for PostgreSQL |

Managed databases provide automatic backups, high availability, and security patches.

### Object Storage for Uploads

Instead of a local filesystem, use object storage for uploaded PDFs and exports:

| Cloud | Service |
|-------|---------|
| AWS | Amazon S3 |
| GCP | Google Cloud Storage |
| Azure | Azure Blob Storage |

Configure `UPLOAD_DIR` to point to a mounted bucket or update `pdf_service.py` to use the cloud SDK.

### CDN for the Frontend

Serve the React build from a CDN for better performance:

| Cloud | Service |
|-------|---------|
| AWS | CloudFront + S3 |
| GCP | Cloud CDN + Cloud Storage |
| Azure | Azure CDN + Blob Storage |

Build the React frontend and upload the `build/` directory to the CDN origin bucket.
