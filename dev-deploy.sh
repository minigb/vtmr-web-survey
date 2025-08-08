#!/bin/bash

echo "🚀 Building and deploying vtmr-web-survey..."

# Stop and remove existing container
echo "Stopping existing container..."
sudo docker stop vtmr-web-survey-container 2>/dev/null || true
sudo docker rm vtmr-web-survey-container 2>/dev/null || true

# Build new image
echo "Building Docker image..."
sudo docker build -t vtmr-web-survey .

# Run new container
echo "Starting new container..."
sudo docker run -d -p 5555:5555 --name vtmr-web-survey-container vtmr-web-survey

# Show status
echo "✅ Deployment complete!"
echo "🌐 App URL: http://mac-chopin9.kaist.ac.kr:5555"
echo "📋 Container status:"
sudo docker ps | grep vtmr-web-survey-container
echo "📊 Logs:"
sudo docker logs vtmr-web-survey-container

echo ""
echo "Quick commands:"
echo "  View logs: sudo docker logs -f vtmr-web-survey-container"
echo "  Stop app:  sudo docker stop vtmr-web-survey-container"
echo "  Restart:   ./dev-deploy.sh" 