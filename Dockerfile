# Build stage - build Evidence with data
FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY evidence-reports/package*.json ./evidence-reports/

# Install dependencies
WORKDIR /app/evidence-reports
RUN npm ci

# Copy data and evidence source
WORKDIR /app
COPY data/ ./data/
COPY evidence-reports/ ./evidence-reports/

# Build Evidence (generates static files)
WORKDIR /app/evidence-reports
RUN npm run sources && npm run build

# Production stage - serve static files
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/evidence-reports/build /usr/share/nginx/html

# Copy nginx config for SPA routing
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ $uri.html /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
