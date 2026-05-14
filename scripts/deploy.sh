#!/bin/bash
# GST API Engine - Full VPS Deploy Script
# Usage: bash scripts/deploy.sh [--ssl]
# Prerequisites: Docker & Docker Compose installed on VPS, Flutter SDK for frontend builds

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "============================================="
echo "  GST API Engine - VPS Deployer"
echo "============================================="
echo ""

# ---- Configuration ----
REPO_DIR="/opt/gst-api-engine"
DOMAIN_API="api.apexbooks.in"
DOMAIN_WEB="apexbooks.in"
INSTALL_SSL=${1:-""}

# ---- Pre-flight checks ----
echo -e "${YELLOW}Pre-flight checks...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not found.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker $(docker --version 2>&1 | cut -d',' -f1)${NC}"

if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}ERROR: Docker Compose not found.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose found${NC}"

# Check ports
for port in 80 443; do
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "${YELLOW}⚠ Port ${port} is in use — stop existing web server first${NC}"
    else
        echo -e "${GREEN}✓ Port ${port} is free${NC}"
    fi
done

# Check if ports 5432, 6379, 9000 are free
for port in 5432 6379 9000; do
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "${YELLOW}⚠ Port ${port} in use (PostgreSQL/Redis/MinIO)${NC}"
    else
        echo -e "${GREEN}✓ Port ${port} is free${NC}"
    fi
done

# ---- Setup repo ----
echo ""
echo -e "${YELLOW}Setting up repo...${NC}"
mkdir -p "$REPO_DIR"
cd "$REPO_DIR"

if [ -d ".git" ]; then
    echo "Pulling latest changes..."
    git pull origin main
else
    echo -e "${RED}Please clone repository first.${NC}"
    exit 1
fi

# ---- Generate secrets ----
echo ""
echo -e "${YELLOW}Generating secrets...${NC}"
mkdir -p secrets
if [ ! -f secrets/jwt_private.pem ]; then
    openssl genrsa -out secrets/jwt_private.pem 2048 2>/dev/null
    openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem 2>/dev/null
    echo -e "${GREEN}✓ JWT key pair generated${NC}"
else
    echo -e "${GREEN}✓ JWT keys already exist${NC}"
fi

POSTGRES_PASSWORD=$(openssl rand -base64 16)
MINIO_ACCESS=$(openssl rand -hex 16)
MINIO_SECRET=$(openssl rand -hex 32)

# ---- Create .env ----
cat > .env <<EOF
APP_NAME=GST API Engine
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://postgres:${POSTGRES_PASSWORD}@db:5432/gst_engine
REDIS_URL=redis://redis:6379/0
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/run/secrets/jwt_public.pem
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=15
ALLOWED_ORIGINS=["https://${DOMAIN_WEB}","https://${DOMAIN_API}"]
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
S3_ENDPOINT=http://minio:9000
S3_BUCKET=gst-api-engine
S3_ACCESS_KEY=${MINIO_ACCESS}
S3_SECRET_KEY=${MINIO_SECRET}
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
MINIO_ROOT_USER=${MINIO_ACCESS}
MINIO_ROOT_PASSWORD=${MINIO_SECRET}
EOF

echo -e "${GREEN}✓ .env created${NC}"

# ---- Create frontend directory ----
mkdir -p frontend_html
echo -e "${YELLOW}Build the Flutter frontend and copy files to ${REPO_DIR}/frontend_html/${NC}"
echo "  See BUILD_FRONTEND.md for instructions"
if [ ! "$(ls -A frontend_html 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠ frontend_html/ is empty — build Flutter web first!${NC}"
else
    echo -e "${GREEN}✓ Frontend files detected ($(ls frontend_html | wc -l) files)${NC}"
fi

# ---- Build and start containers ----
echo ""
echo -e "${YELLOW}Building and starting containers...${NC}"
docker compose up --build -d

# ---- Wait for services ----
echo "Waiting for services to start (20s)..."
sleep 20

# ---- Health check ----
echo ""
echo -e "${YELLOW}Running health check...${NC}"
for i in 1 2 3 4 5; do
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is live${NC}"
        break
    fi
    if [ $i -eq 5 ]; then
        echo -e "${RED}⚠ API health check failed. Check: docker compose logs api${NC}"
    fi
    sleep 3
done

echo ""
echo -e "${GREEN}✓ Deploy complete!${NC}"
echo ""
echo "  API:      http://${DOMAIN_API}  (or http://<VPS_IP>)"
echo "  Frontend: http://${DOMAIN_WEB}   (or http://<VPS_IP>)"
echo "  MinIO:    http://<VPS_IP>:9000/console"
echo "  Docs:     http://${DOMAIN_API}/docs"
echo ""
echo "--- Save these credentials ---"
echo "  POSTGRES_PASSWORD = ${POSTGRES_PASSWORD}"
echo "  MinIO Console: minioadmin / ${MINIO_SECRET}"
echo ""
echo "--- Useful commands ---"
echo "  docker compose logs -f api            # Watch API logs"
echo "  docker compose exec api bash          # Shell into API"
echo "  docker compose exec db psql -U postgres gst_engine  # DB shell"
echo "  docker compose down                   # Stop all"
echo "  docker compose up -d                  # Restart"