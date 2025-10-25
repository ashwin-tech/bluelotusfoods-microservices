#!/bin/bash
set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="${GCP_REGION:-us-central1}"
REPOSITORY="bluelotusfoods"

echo "================================================"
echo "Blue Lotus Foods - Cloud Run Deployment"
echo "================================================"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "Error: Not logged in to gcloud"
    echo "Run: gcloud auth login"
    exit 1
fi

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo ""
echo "Enabling required Google Cloud APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com

# Create Artifact Registry repository if it doesn't exist
echo ""
echo "Creating Artifact Registry repository..."
if ! gcloud artifacts repositories describe $REPOSITORY --location=$REGION &> /dev/null; then
    gcloud artifacts repositories create $REPOSITORY \
        --repository-format=docker \
        --location=$REGION \
        --description="Blue Lotus Foods microservices container images"
    echo "✓ Repository created"
else
    echo "✓ Repository already exists"
fi

# Configure Docker authentication
echo ""
echo "Configuring Docker authentication..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Create secrets (if they don't exist)
echo ""
echo "Setting up secrets..."
echo "Note: You'll need to create these secrets manually with actual values:"
echo ""
echo "  # Database password"
echo "  echo -n 'YOUR_DB_PASSWORD' | gcloud secrets create db-password --data-file=-"
echo ""
echo "  # SMTP credentials"
echo "  echo -n 'YOUR_SMTP_USERNAME' | gcloud secrets create smtp-username --data-file=-"
echo "  echo -n 'YOUR_SMTP_PASSWORD' | gcloud secrets create smtp-password --data-file=-"
echo ""

read -p "Have you created the secrets? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please create the secrets first, then run this script again."
    exit 1
fi

# Build and push bluelotusfoods-email first (API depends on it)
echo ""
echo "================================================"
echo "Building and deploying bluelotusfoods-email..."
echo "================================================"
cd bluelotusfoods-email

echo "Building container image..."
gcloud builds submit \
    --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/bluelotusfoods-email:latest \
    --timeout=20m

echo "Deploying to Cloud Run..."
# Update the YAML file with actual project ID
sed "s/PROJECT_ID/${PROJECT_ID}/g" ../cloudrun-email.yaml > /tmp/cloudrun-email.yaml

gcloud run services replace /tmp/cloudrun-email.yaml \
    --region=$REGION

echo "Setting IAM policy to allow unauthenticated access..."
gcloud run services add-iam-policy-binding bluelotusfoods-email \
    --region=$REGION \
    --member="allUsers" \
    --role="roles/run.invoker"

EMAIL_SERVICE_URL=$(gcloud run services describe bluelotusfoods-email \
    --region=$REGION \
    --format="value(status.url)")

echo "✓ Email service deployed: $EMAIL_SERVICE_URL"

# Build and push bluelotusfoods-api
echo ""
echo "================================================"
echo "Building and deploying bluelotusfoods-api..."
echo "================================================"
cd ../bluelotusfoods-api

echo "Building container image..."
gcloud builds submit \
    --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/bluelotusfoods-api:latest \
    --timeout=20m

echo "Deploying to Cloud Run..."
# Update the YAML file with actual project ID and email service URL
sed "s/PROJECT_ID/${PROJECT_ID}/g" ../cloudrun-api.yaml | \
    sed "s|https://bluelotusfoods-email-PROJECT_ID.a.run.app|${EMAIL_SERVICE_URL}|g" > /tmp/cloudrun-api.yaml

gcloud run services replace /tmp/cloudrun-api.yaml \
    --region=$REGION

echo "Setting IAM policy to allow unauthenticated access..."
gcloud run services add-iam-policy-binding bluelotusfoods-api \
    --region=$REGION \
    --member="allUsers" \
    --role="roles/run.invoker"

API_SERVICE_URL=$(gcloud run services describe bluelotusfoods-api \
    --region=$REGION \
    --format="value(status.url)")

echo "✓ API service deployed: $API_SERVICE_URL"

# Summary
echo ""
echo "================================================"
echo "Deployment Complete!"
echo "================================================"
echo ""
echo "Service URLs:"
echo "  API:   $API_SERVICE_URL"
echo "  Email: $EMAIL_SERVICE_URL"
echo ""
echo "Test your services:"
echo "  curl $API_SERVICE_URL/health"
echo "  curl $EMAIL_SERVICE_URL/health"
echo ""
echo "Next steps:"
echo "  1. Update your frontend env vars:"
echo "     VITE_API_BASE_URL=$API_SERVICE_URL"
echo ""
echo "  2. Set up custom domain (optional):"
echo "     gcloud run domain-mappings create \\"
echo "       --service bluelotusfoods-api \\"
echo "       --domain api.thebluelotusfoods.com \\"
echo "       --region $REGION"
echo ""
echo "  3. Update CORS in API service env vars if needed"
echo ""
