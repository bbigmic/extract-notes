#!/bin/bash
# runpod-deploy.sh

echo "🚀 Deploying to RunPod..."

# Sprawdź czy runpod CLI jest zainstalowane
if ! command -v runpod &> /dev/null; then
    echo "Installing RunPod CLI..."
    pip install runpod
fi

# Zaloguj się do RunPod
echo "Logging in to RunPod..."
runpod login

# Utwórz template
echo "Creating template..."
runpod template create --name "extract-content-app" --dockerfile "Dockerfile"

# Deploy aplikacji
echo "Deploying application..."
runpod pod create --template "extract-content-app" --gpu-type "RTX 4090" --name "extract-content-prod"

echo "✅ Deployment completed!"
