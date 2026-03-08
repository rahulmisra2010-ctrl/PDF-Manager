# Cloud Deployment

This guide covers deploying PDF Manager to AWS, GCP, and Azure using managed container services.

!!! tip "Start with Docker"
    Before deploying to the cloud, ensure you can run the application locally with Docker Compose. See [Docker Installation](docker.md).

---

## AWS – Elastic Container Service (ECS)

### Prerequisites

- AWS CLI configured (`aws configure`)
- AWS account with permissions to ECS, ECR, RDS, and ALB

### Step 1 – Push Images to ECR

```bash
# Authenticate
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push backend
docker build -t pdf-manager-backend .
docker tag pdf-manager-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/pdf-manager-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/pdf-manager-backend:latest
```

### Step 2 – Create an RDS PostgreSQL Instance

```bash
aws rds create-db-instance \
  --db-instance-identifier pdf-manager-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username pdfmanager \
  --master-user-password <strong-password> \
  --allocated-storage 20
```

### Step 3 – Create ECS Cluster and Service

Use the AWS Console or CLI to create a Fargate cluster with the backend and frontend task definitions. Set environment variables from AWS Secrets Manager or Parameter Store.

### Step 4 – Configure Application Load Balancer

Create an ALB that routes:

- `/*` → frontend target group (port 3000)
- `/api/*` → backend target group (port 5000)
- `/auth/*` → backend target group (port 5000)

---

## Google Cloud Platform – Cloud Run

### Prerequisites

- `gcloud` CLI installed and authenticated
- Project with Cloud Run, Artifact Registry, and Cloud SQL APIs enabled

### Step 1 – Build and Push to Artifact Registry

```bash
# Configure Docker for GCP
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push
docker build -t us-central1-docker.pkg.dev/<project>/pdf-manager/backend:latest .
docker push us-central1-docker.pkg.dev/<project>/pdf-manager/backend:latest
```

### Step 2 – Create Cloud SQL PostgreSQL

```bash
gcloud sql instances create pdf-manager \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1
```

### Step 3 – Deploy to Cloud Run

```bash
gcloud run deploy pdf-manager-backend \
  --image us-central1-docker.pkg.dev/<project>/pdf-manager/backend:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=postgresql://..." \
  --set-secrets "SECRET_KEY=pdf-manager-secret:latest"
```

---

## Azure – Container Apps

### Prerequisites

- Azure CLI installed and authenticated
- Resource group and Container Apps environment created

### Step 1 – Push to Azure Container Registry

```bash
az acr login --name <registry-name>
docker tag pdf-manager-backend <registry-name>.azurecr.io/pdf-manager-backend:latest
docker push <registry-name>.azurecr.io/pdf-manager-backend:latest
```

### Step 2 – Create Azure Database for PostgreSQL

```bash
az postgres flexible-server create \
  --resource-group pdf-manager-rg \
  --name pdf-manager-db \
  --admin-user pdfmanager \
  --admin-password <strong-password> \
  --sku-name Standard_B1ms
```

### Step 3 – Create Container App

```bash
az containerapp create \
  --resource-group pdf-manager-rg \
  --name pdf-manager-backend \
  --environment pdf-manager-env \
  --image <registry-name>.azurecr.io/pdf-manager-backend:latest \
  --target-port 5000 \
  --ingress external \
  --env-vars "DATABASE_URL=postgresql://..."
```

---

## Security Considerations

- Store `SECRET_KEY` and `ADMIN_PASSWORD` in a secrets manager (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault).
- Use managed TLS via your cloud provider's load balancer.
- Restrict database access to the application's security group/VPC.
- Enable VPC/private networking for backend-to-database communication.

## Next Steps

- [SSL/TLS Setup](../deployment/ssl.md)
- [Monitoring](../deployment/monitoring.md)
- [Backup & Recovery](../deployment/backup.md)
