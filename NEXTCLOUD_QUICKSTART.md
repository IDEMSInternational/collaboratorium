# NextCloud & Collabora Setup Guide

## Quick Start (10 minutes)

### 1. Environment Setup
```bash
cp env.example .env
# Edit .env with strong passwords for:
# - NEXTCLOUD_ADMIN_PASSWORD
# - NEXTCLOUD_DB_PASSWORD
# - NEXTCLOUD_DB_ROOT_PASSWORD
```

### 2. Config Setup
In `config.yaml`:
```yaml
# NextCloud and Collabora Online Integration
nextcloud:
  # Base URL of your NextCloud instance
  url: "https://nextcloud.your-domain"
  # Default folder for storing reports (relative to user root in NextCloud)
  default_folder: "/Collaboratorium%20Reports"
  group_folder: True
  # Path to template document for report generation
  default_template: "/Collaboratorium%20Reports/template.odt"
  verify_ssl: False
```

### 3. Start Services

```bash
docker-compose up -d
```

Initialization scripts in the 'nextcloud' service will automatically:
- Enable GroupFolders app (collaborative document storage)
- Enable NextCloud Office (integrates with Collabora)
- Configure Collabora server URL

Check the logs of the 'nextcloud' service for the messages, "Initializing finished" and "ready to handle connections".
```
docker compose logs -f nextcloud
```

At this point, Nextcloud should be ready to use.

Assuming the `DOMAIN` environment variable is set to 'idems', append the following line to your 'hosts' file:
```
127.0.0.1 collabora.idems dash.idems nextcloud.idems idems
```

In a browser, visit <https://collabora.idems/> - the browser will likely show a security warning due to the self-signed TLS certificate. Make an exception for this domain.

Visit <https://nextcloud.idems/>. Make security exception, if necessary. Log in using the username and password you set earlier.

### 4. Setup NextCloud

Open `https://your-domain/nextcloud`:
1. Log in as admin (credentials from `.env`)
2. Go to Settings → Security → "Create new app password"
3. Copy the generated password
4. Update `.env`: `NEXTCLOUD_APP_PASSWORD=<copied_password>`
5. Restart: `docker-compose restart collaboratorium`

### 5. Create Folder Structure
In NextCloud, create the folders you specified in step 2, and upload a template document.

## Key Components

### Documents
- Stored in NextCloud group folder (`/group-folders/1/Reports/`)
- Shared by default (collaborative)
- Edit in browser via Collabora Online

### Apps Auto-Installed
- **GroupFolders**: Collaborative group storage
- **NextCloud Office**: Document editing integration
- **Collabora Online**: Real-time editor via existing Docker service

## Configuration


### Add Multiple Document Types
Insert into `tag_groups` table with different:
- `folder_path` (e.g., `/Minutes`, `/Reports`)
- `template_path` (different templates)
- `activity_id` (custom prefix)

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Could not connect" | Check `docker logs nextcloud` |
| "401 Unauthorized" | Verify `NEXTCLOUD_APP_PASSWORD` in `.env` and re-enter in app |
| "Template not found" | Check path exists in NextCloud, verify `/Templates/report_template.odt` |
| "Collabora won't load" | Check `docker logs collabora`, verify `https://collabora.localhost` accessible |
| "Group folder missing" | Check `docker logs nextcloud` during startup, see `nextcloud_hooks/README.md` |

## Manage Document Access

1. Go to NextCloud → Administration → Group folders
2. Click "collaboratorium" folder
3. Add groups and set permissions (Read, Write, Share, Delete)
4. Users in those groups access all documents in folder

## Backup

```bash
docker exec nextcloud tar -czf /tmp/backup.tar.gz /var/www/html
docker cp nextcloud:/tmp/backup.tar.gz ./backups/
```

## Next Steps

For advanced configuration, see:
- `nextcloud_hooks/README.md` - Auto-app-installation details
- `docs/nextcloud_integration.md` - Full technical documentation
