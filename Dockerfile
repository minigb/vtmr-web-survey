FROM node:18-alpine
WORKDIR /app

# Install Python3 and curl for video metadata generation and API calls
RUN apk add --no-cache python3 curl

COPY package.json package-lock.json* ./
RUN npm install --production
COPY . .
EXPOSE 5555

# Create a startup script that starts server, generates video metadata, then refreshes mappings
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'echo "🚀 Starting server in background..."' >> /app/start.sh && \
    echo 'node /app/server.js &' >> /app/start.sh && \
    echo 'SERVER_PID=$!' >> /app/start.sh && \
    echo 'sleep 2' >> /app/start.sh && \
    echo 'echo "🎬 Generating video metadata..."' >> /app/start.sh && \
    echo 'python3 /app/generate_video_metadata.py' >> /app/start.sh && \
    echo 'echo "📋 Refreshing video mappings..."' >> /app/start.sh && \
    echo 'curl -s -X POST http://localhost:5555/api/refresh-mappings > /dev/null || true' >> /app/start.sh && \
    echo 'echo "✅ Ready to serve surveys with anonymous videos!"' >> /app/start.sh && \
    echo 'wait $SERVER_PID' >> /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]
