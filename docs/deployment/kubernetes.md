# Kubernetes Deployment

This guide deploys PDF Manager to a Kubernetes cluster.

## Prerequisites

- `kubectl` configured for your cluster
- Container images pushed to a registry (Docker Hub, ECR, GCR, ACR)
- A PostgreSQL instance (managed cloud DB or in-cluster)

## Namespace

```bash
kubectl create namespace pdf-manager
```

## Secret

```bash
kubectl create secret generic pdf-manager-secrets \
  --namespace pdf-manager \
  --from-literal=SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=ADMIN_PASSWORD="<strong-password>" \
  --from-literal=DATABASE_URL="postgresql://pdfmanager:<password>@<db-host>:5432/pdfmanager"
```

## Backend Deployment

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pdf-manager-backend
  namespace: pdf-manager
spec:
  replicas: 2
  selector:
    matchLabels:
      app: pdf-manager-backend
  template:
    metadata:
      labels:
        app: pdf-manager-backend
    spec:
      containers:
        - name: backend
          image: your-registry/pdf-manager-backend:latest
          ports:
            - containerPort: 5000
          env:
            - name: DEBUG
              value: "false"
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: pdf-manager-secrets
                  key: SECRET_KEY
            - name: ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: pdf-manager-secrets
                  key: ADMIN_PASSWORD
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: pdf-manager-secrets
                  key: DATABASE_URL
          volumeMounts:
            - name: uploads
              mountPath: /app/uploads
          livenessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 15
            periodSeconds: 20
      volumes:
        - name: uploads
          persistentVolumeClaim:
            claimName: pdf-manager-uploads
---
apiVersion: v1
kind: Service
metadata:
  name: pdf-manager-backend
  namespace: pdf-manager
spec:
  selector:
    app: pdf-manager-backend
  ports:
    - port: 5000
      targetPort: 5000
```

## Persistent Volume Claim

```yaml
# k8s/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pdf-manager-uploads
  namespace: pdf-manager
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 20Gi
```

## Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: pdf-manager
  namespace: pdf-manager
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - your-domain.com
      secretName: pdf-manager-tls
  rules:
    - host: your-domain.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: pdf-manager-backend
                port:
                  number: 5000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: pdf-manager-frontend
                port:
                  number: 3000
```

## Deploy

```bash
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/ingress.yaml

# Check status
kubectl get pods -n pdf-manager
kubectl logs -n pdf-manager deployment/pdf-manager-backend
```
