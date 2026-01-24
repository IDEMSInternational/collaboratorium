# NextCloud & Collabora Quick Start Guide

## 5-Minute Setup

### 1. Environment Configuration

Copy and update `.env`:

```bash
cp env.example .env

# Edit .env with strong passwords:
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=your_strong_password_here
NEXTCLOUD_DB_PASSWORD=your_db_password_here
NEXTCLOUD_DB_ROOT_PASSWORD=your_root_password_here
NEXTCLOUD_APP_PASSWORD=will_generate_in_step_3
```

### 2. Start Services

```bash
docker-compose up -d
```

Wait 60 seconds for NextCloud to initialize.

### 3. Generate NextCloud App Password & Setup Session Password

1. Open `https://your-domain/nextcloud` in browser
2. Log in as admin (credentials from `.env`)
3. Click avatar → Settings → Security
4. Under "Devices & sessions", click "Create new app password"
5. Copy the generated password
6. Update `.env`: `NEXTCLOUD_APP_PASSWORD=copied_password`
7. Restart Collaboratorium: `docker-compose restart collaboratorium`

**Important**: You'll also need to enter the app password in the application UI:
1. Open Collaboratorium application
2. Find "NextCloud Password" section in the main panel
3. Paste the app password
4. Click "Save Password"
5. Status should show success message

### 4. Create Template Folder & Document

In NextCloud:

1. Create folder: `/Templates`
2. Upload a document:
   - Use LibreOffice to create `report_template.odt`
   - Or download sample: [Template Example](#)
3. Create folder: `/Reports` (for generated documents)

### 5. Create Subform in Database

```bash
# Connect to database
docker exec -it collaboratorium sqlite3 database.db

# Insert Report subform
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  1,
  1,
  'Report',
  '{"nextcloud_url": {"type": "text", "label": "NextCloud URL"}, "folder_path": {"type": "text", "label": "Folder Path", "default": "/Reports"}, "template_path": {"type": "text", "label": "Template Path", "default": "/Templates/report_template.odt"}, "activity_id": {"type": "text", "label": "Document ID Prefix"}}',
  '1',
  datetime('now'),
  'active',
  1
);

# Exit
.exit
```

### 6. Test in Application

1. Open Collaboratorium (logged in as Google user)
2. Go to Activities table
3. Create or edit an activity
4. Click "Add Subform" → Select "Report"
5. Fill in settings (or use defaults):
   - NextCloud URL: `https://your-domain/nextcloud`
   - Folder Path: `/Reports`
   - Template Path: `/Templates/report_template.odt`
   - Document ID: `activity_123`
6. Click "Create/Open Report"
7. Should see green success message with link
8. Click link to open document in Collabora Online

### 7. (Optional) Test nextcloud_attachments Component

If your form includes a `nextcloud_attachments` element:

1. Go to the same activity form
2. Scroll to "Supporting Documents" or similar section
3. Click "Create New Document" button
4. Document created and automatically added to table
5. Click URL in table to open in Collabora
6. Table persists data across form saves

## Troubleshooting

### "Could not connect to NextCloud"

```bash
# Verify NextCloud is running
docker ps | grep nextcloud

# Check logs
docker logs nextcloud
docker logs nextcloud-db
```

### "Credentials not configured" or "401 Unauthorized"

```bash
# Option 1: Check environment variable
docker exec collaboratorium env | grep NEXTCLOUD_APP_PASSWORD

# Option 2: Enter password in app UI
# - Open Collaboratorium main panel
# - Find "NextCloud Password" section
# - Enter the app password from Step 3
# - Click "Save Password"

# Option 3: Restart with env var set
# 1. Verify .env has correct password
# 2. Run: docker-compose restart collaboratorium
```

### "Could not copy template"

1. Verify template path in NextCloud (should be `/Templates/report_template.odt`)
2. Check that file has read permissions
3. Test WebDAV access:
   ```bash
   curl -X PROPFIND \
     -u admin:password \
     https://localhost/nextcloud/remote.php/dav/files/admin/Templates/
   ```

### Collabora editor won't load

1. Verify Collabora service: `docker ps | grep collabora`
2. Check nginx routing: `docker logs proxy`
3. Ensure document format is supported (ODF, DOCX, XLSX, PPTX)

## Common Operations

### Create New Template

```bash
# 1. In LibreOffice, create document
# 2. Save as .odt format
# 3. Upload to NextCloud at /Templates/
# 4. Update tag group template_path if needed
```

### Add Multiple Subform Types

Example: Create "Meeting Minutes" subform

```sql
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  2,
  1,
  'Meeting Minutes',
  '{"nextcloud_url": {"type": "text"}, "folder_path": {"type": "text", "default": "/Minutes"}, "template_path": {"type": "text", "default": "/Templates/minutes_template.odt"}, "activity_id": {"type": "text"}}',
  '1',
  datetime('now'),
  'active',
  1
);
```

### Monitor Document Usage

Documents stored in NextCloud at:
```
/admin/Reports/activity_123_20250120_143022.odt
/admin/Reports/activity_124_20250120_144015.odt
```

Each document is timestamped and associated with the activity ID.

### Backup Documents

```bash
# Backup NextCloud data
docker exec nextcloud tar -czf /tmp/nextcloud_backup.tar.gz /var/www/html

# Copy to host
docker cp nextcloud:/tmp/nextcloud_backup.tar.gz ./backups/
```

## Advanced Configuration

See `docs/nextcloud_integration.md` for:
- Custom WebDAV client options
- Performance tuning
- LDAP/OAuth integration
- Multi-language support
- Document conversion options

## Support

Issues? Check:
1. `docs/nextcloud_integration.md` - Full documentation
2. `NEXTCLOUD_IMPLEMENTATION.md` - Implementation details
3. Application logs: `docker logs collaboratorium`
4. NextCloud logs: `docker logs nextcloud`
5. Proxy logs: `docker logs proxy`
