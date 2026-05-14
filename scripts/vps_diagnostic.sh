#!/bin/bash
# VPS Diagnostic Commands — GST API Engine
# SSH into VPS first, then run these commands
# ============================================================

echo ""
echo "============================================="
echo "  VPS DIAGNOSTIC REPORT — GST API Engine"
echo "============================================="
echo ""

# ---- 1. SYSTEM OVERVIEW ----
echo "━━━ 1. SYSTEM OVERVIEW ━━━"
echo "Hostname:     $(hostname)"
echo "Uptime:       $(uptime -p 2>/dev/null || uptime)"
echo "OS:           $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "Kernel:       $(uname -r)"
echo "CPU Cores:    $(nproc)"
echo "Memory:       $(free -h | awk '/Mem:/ {print $3 " / " $2}')"
echo "Disk:         $(df -h / | awk 'NR==2 {print $3 " / " $2 " (" $5 " used)"}')"
echo ""

# ---- 2. DOCKER STATUS ----
echo "━━━ 2. DOCKER STATUS ━━━"
echo ""
echo "--- Docker Service ---"
sudo systemctl is-active docker && echo "  ✅ Docker is running" || echo "  ❌ Docker is NOT running"
sudo systemctl is-enabled docker && echo "  ✅ Docker enabled on boot" || echo "  ⚠ Docker not enabled on boot"
echo ""

echo "--- Running Containers ---"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "--- All Containers (incl stopped) ---"
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "--- Docker Compose Project (if in /opt/gst-api-engine) ---"
cd /opt/gst-api-engine 2>/dev/null && docker compose ps 2>/dev/null || echo "  (not in compose directory)"
echo ""

# ---- 3. CONTAINER LOGS ----
echo "━━━ 3. CONTAINER LOGS (last 30 lines each) ━━━"
for container in api worker scheduler nginx db redis minio; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}"; then
        echo ""
        echo "--- $container ---"
        docker logs --tail 30 "$container" 2>&1 | tail -30
    fi
done
echo ""

# ---- 4. PORT USAGE ----
echo "━━━ 4. PORT USAGE ━━━"
echo ""
echo "--- All listening ports ---"
ss -tlnp | awk 'NR>1 {printf "  %-6s %-22s %s\n", $1, $4, $7}'
echo ""

echo "--- Key ports check ---"
for port in 22 80 443 8000 5432 6379 9000 9001; do
    if ss -tlnp | grep -q ":${port} "; then
        process=$(ss -tlnp | grep ":${port} " | awk '{print $7}')
        echo "  ✅ Port $port in use → $process"
    else
        echo "  ⬜ Port $port free"
    fi
done
echo ""

# ---- 5. NGINX STATUS ----
echo "━━━ 5. NGINX STATUS ━━━"
sudo systemctl is-active nginx 2>/dev/null && echo "  ✅ Nginx running (systemd)" || echo "  ❌ Nginx not running (systemd)"
docker ps --format '{{.Names}}' | grep -q nginx && echo "  ✅ Nginx container running (Docker)" || echo "  ⬜ Nginx not in Docker (may be system-level)"
echo ""

echo "--- Nginx Config Check ---"
sudo nginx -t 2>&1
echo ""

echo "--- Active Nginx Configs ---"
ls -la /etc/nginx/conf.d/ 2>/dev/null || ls -la /etc/nginx/sites-enabled/ 2>/dev/null || echo "  (checking Docker configs)"
docker exec nginx cat /etc/nginx/conf.d/default.conf 2>/dev/null | head -30 || echo "  (no nginx container or config)"
echo ""

# ---- 6. DOMAIN / DNS CHECK ----
echo "━━━ 6. DOMAIN & DNS ━━━"
echo "--- DNS Resolution ---"
for domain in api.apexbooks.in apexbooks.in www.apexbooks.in; do
    ip=$(dig +short "$domain" 2>/dev/null | head -1)
    if [ -n "$ip" ]; then
        echo "  ✅ $domain → $ip"
    else
        echo "  ❌ $domain → NOT RESOLVING"
    fi
done
echo ""

echo "--- SSL Certificates ---"
for domain in api.apexbooks.in apexbooks.in; do
    if [ -f "/etc/letsencrypt/live/$domain/fullchain.pem" ]; then
        echo "  ✅ $domain — cert exists, expires: $(openssl x509 -enddate -noout -in /etc/letsencrypt/live/$domain/cert.pem 2>/dev/null | cut -d= -f2)"
    else
        echo "  ⚠  $domain — no Let's Encrypt cert found"
    fi
done
echo ""

# ---- 7. POSTGRESQL ----
echo "━━━ 7. POSTGRESQL ━━━"
docker exec db pg_isready 2>/dev/null && echo "  ✅ PostgreSQL is accepting connections" || echo "  ❌ PostgreSQL not responding"
docker exec db psql -U postgres -d gst_engine -c "SELECT count(*) as table_count FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "  ⚠ Could not query database"
echo ""

# ---- 8. REDIS ----
echo "━━━ 8. REDIS ━━━"
docker exec redis redis-cli ping 2>/dev/null && echo "  ✅ Redis is responding" || echo "  ❌ Redis not responding"
echo ""

# ---- 9. MINIO ----
echo "━━━ 9. MINIO ━━━"
curl -sf http://localhost:9000/minio/health/cluster 2>/dev/null && echo "  ✅ MinIO is healthy" || echo "  ❌ MinIO not responding"
echo ""

# ---- 10. API HEALTH ----
echo "━━━ 10. API HEALTH ━━━"
echo "--- Direct (port 8000) ---"
curl -sf http://localhost:8000/health 2>/dev/null && echo "" || echo "  ❌ API not responding on :8000"
echo ""
echo "--- Via Nginx (port 80) ---"
curl -sf http://localhost/health 2>/dev/null && echo "" || echo "  ❌ API not responding via nginx"
echo ""

# ---- 11. FIREWALL ----
echo "━━━ 11. FIREWALL ━━━"
if command -v ufw &> /dev/null; then
    sudo ufw status 2>/dev/null | head -20
elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --list-all 2>/dev/null | head -20
else
    echo "  (no firewall utility found)"
fi
echo ""

echo "============================================="
echo "  END OF DIAGNOSTIC REPORT"
echo "============================================="