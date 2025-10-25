# Blue Lotus Foods - Google Cloud Run Deployment

This directory contains Cloud Run configuration for deploying the Blue Lotus Foods microservices.

## Files

- `cloudrun-api.yaml` - Cloud Run service configuration for the main API
- `cloudrun-email.yaml` - Cloud Run service configuration for the email service
- `deploy-cloudrun.sh` - Automated deployment script

## Prerequisites

1. **Google Cloud Project**
   - Create a project at https://console.cloud.google.com
   - Enable billing for the project

2. **Install gcloud CLI**
   ```bash
   # macOS
   brew install --cask google-cloud-sdk
   
   # Or download from: https://cloud.google.com/sdk/docs/install
   ```

3. **Authenticate**
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

4. **Set up PostgreSQL Database**
   
   Option A - Cloud SQL (managed):
   ```bash
   gcloud sql instances create blf-postgres \
     --database-version=POSTGRES_15 \
     --tier=db-f1-micro \
     --region=us-central1
   
   gcloud sql databases create bluelotusfoods \
     --instance=blf-postgres
   
   gcloud sql users create blf_user \
     --instance=blf-postgres \
     --password=YOUR_PASSWORD
   ```
   
   Option B - External database (update DB_HOST in YAML files)

## Quick Start

### 1. Create Secrets

```bash
# Database password
echo -n 'YOUR_DB_PASSWORD' | gcloud secrets create db-password --data-file=-

# SMTP credentials
echo -n 'your-email@gmail.com' | gcloud secrets create smtp-username --data-file=-
echo -n 'YOUR_APP_PASSWORD' | gcloud secrets create smtp-password --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:PROJECT_ID-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding smtp-username \
  --member="serviceAccount:PROJECT_ID-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding smtp-password \
  --member="serviceAccount:PROJECT_ID-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 2. Update Configuration

Edit `cloudrun-api.yaml` and `cloudrun-email.yaml`:
- Replace `PROJECT_ID` with your GCP project ID
- Update `DB_HOST` with your database host
- Update `CORS_ORIGINS` with your frontend domain

### 3. Deploy

**Automated deployment:**
```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-central1
./deploy-cloudrun.sh
```

**Manual deployment:**
```bash
# Build and push images
cd bluelotusfoods-email
gcloud builds submit --tag us-central1-docker.pkg.dev/PROJECT_ID/bluelotusfoods/bluelotusfoods-email

cd ../bluelotusfoods-api
gcloud builds submit --tag us-central1-docker.pkg.dev/PROJECT_ID/bluelotusfoods/bluelotusfoods-api

# Deploy services
gcloud run services replace cloudrun-email.yaml --region=us-central1
gcloud run services replace cloudrun-api.yaml --region=us-central1

# Allow unauthenticated access
gcloud run services add-iam-policy-binding bluelotusfoods-email \
  --region=us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker"

gcloud run services add-iam-policy-binding bluelotusfoods-api \
  --region=us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

### 4. Get Service URLs

```bash
# API service
gcloud run services describe bluelotusfoods-api \
  --region=us-central1 \
  --format="value(status.url)"

# Email service
gcloud run services describe bluelotusfoods-email \
  --region=us-central1 \
  --format="value(status.url)"
```

### 5. Test Deployment

```bash
# Test API
curl https://bluelotusfoods-api-XXXX.a.run.app/health
curl https://bluelotusfoods-api-XXXX.a.run.app/vendors

# Test Email service
curl https://bluelotusfoods-email-XXXX.a.run.app/health
```

## Custom Domain Setup

Map your custom domain to Cloud Run:

```bash
# For API
gcloud run domain-mappings create \
  --service bluelotusfoods-api \
  --domain api.thebluelotusfoods.com \
  --region us-central1

# For Email (optional, usually internal)
gcloud run domain-mappings create \
  --service bluelotusfoods-email \
  --domain email.thebluelotusfoods.com \
  --region us-central1
```

Then add the DNS records shown by Cloud Run to your domain registrar.

## Update Frontend

Update your Vercel environment variables:
```
VITE_API_BASE_URL=https://api.thebluelotusfoods.com
# or
VITE_API_BASE_URL=https://bluelotusfoods-api-XXXX.a.run.app
```

Update API CORS:
```bash
gcloud run services update bluelotusfoods-api \
  --update-env-vars CORS_ORIGINS='["https://www.thebluelotusfoods.com"]' \
  --region us-central1
```

## Cost Optimization

- **Autoscaling**: Services scale to 0 when idle (free tier: 2M requests/month)
- **CPU allocation**: CPU only allocated during request processing
- **Memory limits**: Set to minimum required (256Mi for email, 512Mi for API)
- **Concurrency**: 80 requests per container instance
- **Startup CPU boost**: Faster cold starts

## Monitoring

View logs:
```bash
# API logs
gcloud run logs tail bluelotusfoods-api --region=us-central1

# Email logs
gcloud run logs tail bluelotusfoods-email --region=us-central1
```

View metrics in Cloud Console:
- https://console.cloud.google.com/run

## CI/CD with GitHub Actions

Want automatic deployments on git push? See the GitHub Actions workflow example in `.github/workflows/deploy-cloudrun.yml` (coming soon).

## Troubleshooting

**Build fails:**
- Check Dockerfile syntax
- Ensure all dependencies are in requirements.txt

**Service won't start:**
- Check logs: `gcloud run logs tail SERVICE_NAME --region=us-central1`
- Verify environment variables and secrets
- Test container locally: `docker build -t test . && docker run -p 8000:8000 test`

**Database connection fails:**
- For Cloud SQL: Use Cloud SQL Proxy or Private IP
- Check DB_HOST, DB_USER, DB_PASSWORD in secrets
- Verify firewall rules

**CORS errors:**
- Update CORS_ORIGINS environment variable
- Ensure frontend domain is included

## Support

For issues specific to:
- Cloud Run: https://cloud.google.com/run/docs
- Cloud SQL: https://cloud.google.com/sql/docs
- Secret Manager: https://cloud.google.com/secret-manager/docs
