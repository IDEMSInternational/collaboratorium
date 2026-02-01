# Nginx Multi-App Setup

Three applications running on separate subdomains using Nginx reverse proxy with SSL.

## Quick Start

### 1. Update Hosts File
Add these lines to your hosts file:

**Windows:** `C:\Windows\System32\drivers\etc\hosts`
**Linux/Mac:** `/etc/hosts`

```
127.0.0.1    localhost
127.0.0.1    dash.localhost
127.0.0.1    nextcloud.localhost
127.0.0.1    collabora.localhost
```

`ipconfig /flushdns`

### 2. Start Services
```bash
cd c:\Users\gabe\git-repos\collaboratorium
docker-compose down
docker-compose up -d --build
```

### 3. Access Applications
- **Dash:** `https://dash.localhost/`
- **Nextcloud:** `https://nextcloud.localhost/`
- **Collabora:** `https://collabora.localhost/`

(Ignore SSL warnings for localhost - they're expected)

## Configuration

### URLs by Environment

| Environment | Dash | Nextcloud | Collabora |
|---|---|---|---|
| **Local Testing** | `https://dash.localhost/` | `https://nextcloud.localhost/` | `https://collabora.localhost/` |
| **Production** | `https://domain.com/` | `https://nextcloud.domain.com/` | `https://collabora.domain.com/` |

### Environment Variables

In `.env`:
```
DOMAIN=localhost              # For testing. Set to yourdomain.com for production
CERTBOT_EMAIL=your@email.com # For Let's Encrypt
USE_LOCAL_CA=1               # 1 for testing (self-signed), 0 for production (Let's Encrypt)
```

## How It Works

**Nginx** listens on ports 80 and 443, routing requests to the correct backend:

```
HTTP (port 80)  →  Redirect to HTTPS
                ↓
HTTPS (port 443)
  ├─ dash.localhost:443     → Dash app (port 8050)
  ├─ nextcloud.localhost:443 → Nextcloud (port 8080)
  └─ collabora.localhost:443 → Collabora (port 9980)
```

## Nextcloud + Collabora Integration

To enable document editing in Nextcloud:

1. Go to Nextcloud: `https://nextcloud.localhost/`
2. Login with admin credentials (from `.env`)
3. Go to **Settings → Administration → Collabora Online**
4. Set "Collabora Online Server" to: `https://collabora.localhost/`
5. Click "Test Server Connection" - should show green checkmark
6. Upload a document and click to open it - Collabora should load

## Troubleshooting

### "Connection refused" or "Can't reach server"
**Problem:** Hosts file not updated or DNS not resolving

**Solution:**
```bash
# Check hosts file contains entries
cat c:\Windows\System32\drivers\etc\hosts

# On Windows, you may need to flush DNS cache
ipconfig /flushdns

# Verify DNS resolution works
nslookup dash.localhost
nslookup nextcloud.localhost
nslookup collabora.localhost
```

### All subdomains show Dash app
**Problem:** Nginx server name matching issue

**Solution:**
```bash
# Validate Nginx config
docker-compose exec proxy nginx -t

# Restart services
docker-compose restart proxy
```

### Nextcloud shows "Untrusted Domain"
**Problem:** Domain not recognized by Nextcloud

**Solution:**
```bash
# In .env, update NEXTCLOUD_TRUSTED_DOMAINS:
NEXTCLOUD_TRUSTED_DOMAINS="nextcloud.localhost localhost"

# Then restart:
docker-compose restart nextcloud
```

### Collabora shows 400 error
**Problem:** Collabora service not running or misconfigured

**Solution:**
```bash
# Check Collabora logs
docker-compose logs collabora

# Check environment variables are correct
docker-compose exec collabora env | grep -i server_name

# Restart
docker-compose restart collabora
```

### SSL/Certificate errors
**Problem:** Self-signed certificates for localhost

**Solution:** This is normal. In your browser, click "Advanced" and accept the warning. The certificates are self-signed for testing only.

For production, Let's Encrypt certificates are automatically obtained.

## For Colleagues

**To set up locally:**
1. Clone repo and run: `docker-compose up -d --build`
2. Add hosts file entries (above)
3. Visit `https://dash.localhost/`, `https://nextcloud.localhost/`, `https://collabora.localhost/`

**To deploy to production:**
1. Update `.env`: `DOMAIN=yourdomain.com` and `USE_LOCAL_CA=0`
2. Set DNS: `*.yourdomain.com A your.server.ip` (wildcard) or individual records
3. Run: `docker-compose down && docker-compose up -d --build`
4. Let's Encrypt certificates automatically obtained on first run

## Files Modified

- `nginx/default.conf.template` - Nginx configuration
- `docker-compose.yml` - Collabora service environment variables
- `.env` - Configuration values

All changes are backwards compatible and production-ready.
