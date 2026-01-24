# NextCloud and Collabora Online Integration

This document explains how to use the NextCloud and Collabora Online integration in Collaboratorium for collaborative document editing.

## Overview

The integration allows users to:
1. Create collaborative documents stored in NextCloud
2. Edit documents in real-time using Collabora Online (LibreOffice in the Cloud)
3. Store document metadata as JSON in the subform system (no database schema changes)
4. Maintain institutional customization through subform configuration
5. Manage multiple attachments with automatic table updates
6. Enter NextCloud credentials via password input UI

## Architecture

### Component Structure

```
Subform (JSON stored in activities/initiatives/etc.)
├── Report (subform_id from tag_groups)
│   ├── nextcloud_url (customized per institution)
│   ├── folder_path (where documents are stored)
│   ├── template_path (template to copy for new documents)
│   └── activity_id (reference for document naming)

Component Types:
├── nextcloud_doc (single document button)
└── nextcloud_attachments (multi-document table)

Session Management:
└── Flask session['nextcloud_password'] (password input for auth)
```

### Technology Stack

- **NextCloud**: Document storage and WebDAV access
- **Collabora Online**: Real-time collaborative editing
- **Nginx**: Reverse proxy for SSL/TLS and routing
- **Python Requests**: WebDAV client for file operations

## Configuration

### 1. Environment Variables

Add these to your `.env` file:

```bash
# NextCloud Administration
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=strong_password_here
NEXTCLOUD_DB_USER=nextcloud
NEXTCLOUD_DB_PASSWORD=db_password_here
NEXTCLOUD_DB_ROOT_PASSWORD=root_password_here

# NextCloud App Password (for programmatic access)
NEXTCLOUD_APP_PASSWORD=app_specific_password
```

To generate an app password in NextCloud:
1. Log in as an administrator
2. Go to Settings > Security > Devices & sessions
3. Click "Create new app password"
4. Copy the generated password

**Important**: You will need to enter this password BOTH:
1. In the `.env` file for environment configuration
2. In the Collaboratorium application UI under "NextCloud Password" for session-based access

### 2. Configuration (config.yaml)

```yaml
nextcloud:
  url: "https://your-domain.com/nextcloud"
  default_folder: "/Reports"
  default_template: "/Templates/report_template.odt"
```

### 3. Docker Compose

The updated `docker-compose.yml` includes:
- `nextcloud-db`: MariaDB database for NextCloud
- `nextcloud`: NextCloud FPM service
- `collabora`: LibreOffice Collabora Online service

Services are exposed through Nginx reverse proxy.

## Usage

### 1. Add a Report Subform to Activities

In your form configuration (e.g., `activities_form`), include:

```yaml
activities_form:
  label: Activities
  default_table: activities
  elements:
    name:
      type: string
      label: Activity Name
    tag_groups:
      type: subform
      label: Documents
      parameters:
        source_table: tag_groups
        value_column: id
        label_column: name
    attachments:
      type: nextcloud_attachments
      label: Project Documents
      parameters:
        source_table: tag_groups
        value_column: id
        label_column: name
```

### 2. Create Subform in Database

Insert a subform in the `tag_groups` table:

```sql
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  1,
  1,
  'Report',
  '{
    "nextcloud_url": {"type": "text", "label": "NextCloud URL"},
    "folder_path": {"type": "text", "label": "Folder Path", "default": "/Reports"},
    "template_path": {"type": "text", "label": "Template Path", "default": "/Templates/report_template.odt"},
    "activity_id": {"type": "text", "label": "Document ID Prefix"}
  }',
  '1',
  datetime('now'),
  'active',
  1
);
```

### 3. Use in Forms

When editing an activity:
1. Add a "Report" subform (click "Add Subform" dropdown)
2. Configure the NextCloud settings
3. For `nextcloud_doc`: Click "Create/Open Report"
4. For `nextcloud_attachments`: Click "Create New Document"
5. The system will:
   - Create a folder in NextCloud if needed
   - Copy the template document if it doesn't exist
   - Generate a Collabora Online link
   - Display a clickable link to the document (or add to table)

### 4. Enter NextCloud Password (Session)

Before creating documents:
1. Open the main Collaboratorium application
2. Find the "NextCloud Password" section (usually in top panel)
3. Enter your NextCloud app password
4. Click "Save Password"
5. Status should show success message
6. Now document creation calls will work

## API Reference

### `NextCloudClient` Class

```python
client = NextCloudClient(url, username, password)

# Check if file exists
client.check_file_exists(remote_path)

# Copy file via WebDAV
client.copy_file(source_path, dest_path)

# Create folder structure
client.create_folder(folder_path)

# Validate credentials (NEW)
is_valid, error_message = client.validate_credentials()
# Returns: (True, "") on success
#         (False, "error details") on failure
```

### `register_nextcloud_callbacks(app, config)`

Registers Dash callbacks for NextCloud operations.

**Handles**:
- `nextcloud_button` clicks from both component types
- Document creation and file operations
- Intelligent element ID matching for nested components
- Automatic table updates for `nextcloud_attachments`

**Expected config structure:**
```python
{
    'nextcloud': {
        'url': 'https://nextcloud.example.com',
        'default_folder': '/Reports',
        'default_template': '/Templates/report_template.odt'
    }
}
```

### `register_nextcloud_password_callback(app)` (NEW)

Registers callback for NextCloud password input.

**Handles**:
- Password input from UI text field
- Storage in Flask `session['nextcloud_password']`
- Validation and status messages
- Session cleanup on logout

**Usage**:
```python
# Password automatically used by register_nextcloud_callbacks()
password = session.get('nextcloud_password')
if password:
    client = NextCloudClient(url, username, password)
```

### Component: `nextcloud_doc`

Element type for single document creation:

```yaml
elements:
  report:
    type: nextcloud_doc
    label: Create Report
    parameters:
      # (optional - loaded from subform at runtime)
```

The component renders:
- Create/Open Report button
- Configuration store (dcc.Store)
- Hidden file path input
- Status/output display

### Component: `nextcloud_attachments`

Element type for multi-document attachment management:

```yaml
elements:
  attachments:
    type: nextcloud_attachments
    label: Project Documents
    appearance: markdown  # optional
    parameters:
      # (optional - loaded from subform at runtime)
```

The component renders:
- Create New Document button
- DataTable with columns for filename, editor link, etc.
- Auto-update when documents created
- Row deletion capability
- Persistent storage in DataTable.data

**Features**:
- Intelligent element ID matching updates only the correct table
- Supports subform nesting (element ID pattern: subform_id|element_id)
- Read-only table (documents added via button, not direct editing)
- Markdown appearance option for collapsible Details section

## Security Considerations

1. **App Passwords**: Always use app-specific passwords, not user passwords
2. **HTTPS**: Ensure NextCloud is accessed via HTTPS in production
3. **CORS**: Collabora handles frame-ancestors headers via nginx configuration
4. **Authentication**: Uses Google OAuth from Collaboratorium (not separate NextCloud login)
5. **Email-based usernames**: Documents are stored in `/{email_prefix}/` folders

## Troubleshooting

### NextCloud Credentials Not Found

**Error**: "NextCloud credentials not configured" or "401 Unauthorized"

**Solution**: 
- Set `NEXTCLOUD_APP_PASSWORD` in `.env`
- AND enter password in app UI under "NextCloud Password" section
- Verify NextCloud URL in `config.yaml`
- Restart: `docker-compose restart collaboratorium`

### Template Not Found

**Error**: "Could not copy template to NextCloud"

**Solution**:
- Upload template document to NextCloud manually
- Verify path in tag group configuration
- Ensure template has correct format (.odt, .docx, etc.)

### WebDAV Connection Failed

**Error**: "Could not create folder in NextCloud"

**Solution**:
- Verify NextCloud is running: `docker ps`
- Test WebDAV access: `curl -X PROPFIND https://domain/nextcloud/remote.php/dav/files/username/`
- Check nginx logs: `docker logs proxy`

### Collabora Editor Not Loading

**Error**: Document link opens but editor is blank

**Solution**:
- Verify Collabora service is running: `docker ps | grep collabora`
- Check CORS headers in nginx
- Ensure document format is supported (ODF, DOCX, XLSX, PPTX)

## NextCloud Setup

### Initial Setup

1. Access NextCloud at `https://domain/nextcloud`
2. Create admin user with strong password
3. Configure trusted domains if needed
4. Install Collabora Online app from apps store

### Creating Templates

1. Create a folder: `/Templates`
2. Upload your template document (e.g., `report_template.odt`)
3. Set folder path in tag group configuration
4. Ensure documents are in ODF format for best Collabora compatibility

### User Management

For institutional setup:
- Create users in NextCloud for each organization
- Or use LDAP/OAuth integration (beyond this implementation)
- Set app passwords for programmatic access

## Performance Notes

- WebDAV operations are synchronous (blocking)
- Consider adding async task queue for large template copies
- NextCloud database should have adequate resources (2+ GB RAM recommended)
- Collabora needs ~2 CPU cores for concurrent users

## Future Enhancements

Potential improvements:
1. **Async operations**: Use Celery for background document processing
2. **Document versioning**: Track document history in tag groups
3. **Sharing**: Enable document sharing between collaborators
4. **Comments**: Integrate Collabora comments with activity metadata
5. **Export**: Auto-export to PDF after collaboration
6. **Webhooks**: Respond to document changes via NextCloud webhooks

## References

- [NextCloud WebDAV Documentation](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/index.html)
- [Collabora Online Documentation](https://sdk.collaboraonline.com/)
- [LibreOffice API Reference](https://api.libreoffice.org/)
