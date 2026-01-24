# NextCloud Integration - Code Examples

## 1. Using the nextcloud_doc Component in Forms

### Simple Usage (config.yaml)

```yaml
activities_form:
  label: Activities
  default_table: activities
  elements:
    name:
      type: string
      label: Activity Name
    description:
      type: string
      label: Description
    report:
      type: nextcloud_doc
      label: Activity Report
      parameters:
        # Optional - can be overridden in tag group
        source_table: tag_groups
        value_column: id
        label_column: name
```

## 2. Using the nextcloud_attachments Component

The `nextcloud_attachments` component provides a table view of NextCloud documents with the ability to create new documents. Unlike `nextcloud_doc`, this component displays multiple documents in a table format.

### Basic Usage

```yaml
activities_form:
  label: Activities
  elements:
    name:
      type: string
      label: Activity Name
    attachments:
      type: nextcloud_attachments
      label: Project Documents
      parameters:
        source_table: tag_groups
        value_column: id
        label_column: name
```

### With Markdown Appearance

```yaml
activities_form:
  label: Activities
  elements:
    attachments:
      type: nextcloud_attachments
      label: Project Documents
      appearance: markdown
      parameters:
        source_table: tag_groups
        value_column: id
        label_column: name
```

When `appearance: markdown` is set, the component renders with a collapsible Details section instead of a standard table header.

### Component Structure

The `nextcloud_attachments` component includes:
- **Create New Document Button**: Green button to create a new document from template
- **Status Output**: Displays messages and any error information
- **Attachments Table**: Displays list of documents with:
  - Filename
  - Collabora Online editor URL (clickable link)
  - Document size (if available)
  - Row deletion capability
- **Auto-update**: When a new document is created, it automatically appears in the table

### Python Callback Integration

```python
from nextcloud_integration import register_nextcloud_callbacks, register_nextcloud_password_callback

def register_form_callbacks(app, config):
    # ... other registrations ...
    
    # Automatically handles nextcloud_attachments button clicks
    register_nextcloud_callbacks(app, config)
    
    # Password input for NextCloud credentials
    register_nextcloud_password_callback(app)
```

## 3. Advanced Usage with Subforms

```yaml
activities_form:
  label: Activities
  elements:
    name:
      type: string
    tag_groups:
      type: subform
      label: Documents & Metadata
      parameters:
        source_table: tag_groups
        value_column: id
        label_column: name
```

Then in the tag_groups table, create entries:

```sql
-- Report tag group
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  1, 1, 'Report',
  '{
    "nextcloud_url": {"type": "text", "label": "NextCloud URL", "default": "https://example.com/nextcloud"},
    "folder_path": {"type": "text", "label": "Folder Path", "default": "/Reports"},
    "template_path": {"type": "text", "label": "Template Path", "default": "/Templates/report_template.odt"},
    "activity_id": {"type": "text", "label": "Document ID Prefix"}
  }',
  '1',
  datetime('now'),
  'active',
  1
);

-- Meeting Minutes tag group
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  2, 1, 'Meeting Minutes',
  '{
    "nextcloud_url": {"type": "text"},
    "folder_path": {"type": "text", "default": "/Minutes"},
    "template_path": {"type": "text", "default": "/Templates/minutes_template.odt"},
    "activity_id": {"type": "text"}
  }',
  '1',
  datetime('now'),
  'active',
  1
);
```

## 4. NextCloudClient Usage Examples

### Basic Client Initialization

```python
from nextcloud_integration import NextCloudClient

# Initialize
client = NextCloudClient(
    url="https://nextcloud.example.com",
    username="username",
    password="app_password"
)

# Check if file exists
exists = client.check_file_exists("/Reports/document.odt")
print(f"File exists: {exists}")

# Create folder structure
success = client.create_folder("/Reports/2025")
print(f"Folder created: {success}")

# Copy file
success = client.copy_file(
    source_path="/Templates/report_template.odt",
    dest_path="/Reports/report_20250120.odt"
)
print(f"File copied: {success}")

# Validate credentials before operations
is_valid, error_message = client.validate_credentials()
if not is_valid:
    print(f"Authentication failed: {error_message}")
else:
    print("Credentials are valid")
```

### Error Handling

```python
try:
    # Validate credentials first
    is_valid, error = client.validate_credentials()
    if not is_valid:
        print(f"Credential error: {error}")
        return False
    
    if not client.check_file_exists("/Templates/template.odt"):
        print("Template not found!")
        return False
    
    if not client.create_folder("/Reports"):
        print("Failed to create folder")
        return False
    
    if not client.copy_file("/Templates/template.odt", "/Reports/new_doc.odt"):
        print("Failed to copy template")
        return False
        
    print("Document created successfully")
    return True
    
except Exception as e:
    print(f"Error: {e}")
    return False
```

## 5. Registering Callbacks

### In form_gen.py

```python
from nextcloud_integration import register_nextcloud_callbacks, register_nextcloud_password_callback

def register_form_callbacks(app, config):
    register_click_callbacks(app, config)
    register_submit_callbacks(app, config.get("forms", {}))
    register_subform_blocks(app, config.get("forms", {}))
    
    # Register NextCloud integration
    register_nextcloud_callbacks(app, config)
    
    # Register NextCloud password input callback
    register_nextcloud_password_callback(app)
```

### NextCloud Password Input

The `register_nextcloud_password_callback()` function handles password input for NextCloud authentication. This is displayed in the main application UI and stores the password in Flask's session for use in callbacks.

```python
# The callback automatically:
# 1. Takes password input from user
# 2. Stores it in session['nextcloud_password']
# 3. Displays status message (success/error)
# 4. Validates that password is not empty

# Password is then used in nextcloud callbacks:
password = session.get('nextcloud_password')
if password:
    client = NextCloudClient(url, username, password)
else:
    return html.Div("NextCloud password not configured. Please enter it in the password field above.", style={'color': 'red'})
```

### Custom Callback Extension

```python
from dash import Input, Output, State, html
from nextcloud_integration import NextCloudClient

def register_custom_nextcloud_logic(app, config):
    """Additional NextCloud callbacks beyond standard integration"""
    
    @app.callback(
        Output("activity-documents", "children"),
        Input("activity-id", "value"),
    )
    def list_activity_documents(activity_id):
        """Show all documents for an activity in NextCloud"""
        if not activity_id:
            return html.Div("Select an activity first")
        
        client = NextCloudClient(
            url=config['nextcloud']['url'],
            username=get_username(),
            password=session.get('nextcloud_password')
        )
        
        # Validate before attempting operations
        is_valid, error = client.validate_credentials()
        if not is_valid:
            return html.Div(f"Authentication failed: {error}", style={'color': 'red'})
        
        folder_path = f"/Reports/activity_{activity_id}"
        
        # TODO: Implement list_folder() in NextCloudClient
        # documents = client.list_folder(folder_path)
        
        return html.Ul([
            html.Li(f"Document: {doc}")
            for doc in []  # documents
        ])
```

## 6. Configuration Examples

### Minimal Setup

```yaml
# config.yaml
nextcloud:
  url: "https://nextcloud.example.com"
```

All other settings use defaults from environment or hardcoded.

### Full Customization

```yaml
# config.yaml
nextcloud:
  url: "https://nextcloud.example.com"
  default_folder: "/CompanyReports"
  default_template: "/Templates/corporate_report.odt"
  
# Environment variables (.env)
NEXTCLOUD_APP_PASSWORD=abc123xyz...
```

### Multiple Templates Per Domain

```sql
-- Templates tag group
INSERT INTO tag_groups (id, version, name, key_values, activities, timestamp, status, created_by)
VALUES (
  10, 1, 'Templates',
  '{
    "template_select": {
      "type": "select_one",
      "label": "Choose Template",
      "options": [
        {"value": "/Templates/report.odt", "label": "Formal Report"},
        {"value": "/Templates/memo.odt", "label": "Memo"},
        {"value": "/Templates/proposal.odt", "label": "Proposal"}
      ]
    }
  }',
  '1',
  datetime('now'),
  'active',
  1
);
```

## 7. WebDAV Operations (Direct Usage)

### Using requests library directly

```python
import requests
from urllib.parse import quote

# Configuration
NEXTCLOUD_URL = "https://nextcloud.example.com"
USERNAME = "user"
PASSWORD = "app_password"

session = requests.Session()
session.auth = (USERNAME, PASSWORD)

# WebDAV base path
dav_base = f"{NEXTCLOUD_URL}/remote.php/dav/files/{quote(USERNAME)}"

# Check file exists (PROPFIND)
response = session.request(
    'PROPFIND',
    f"{dav_base}/Reports/document.odt",
    timeout=5
)
print(f"Exists: {response.status_code in (200, 207)}")

# Create folder (MKCOL)
response = session.request(
    'MKCOL',
    f"{dav_base}/Reports",
    timeout=5
)
print(f"Created: {response.status_code in (200, 201, 204, 405)}")

# Copy file (COPY)
response = session.request(
    'COPY',
    f"{dav_base}/Templates/template.odt",
    headers={'Destination': f"{dav_base}/Reports/new.odt"},
    timeout=10
)
print(f"Copied: {response.status_code in (200, 201, 204)}")
```

## 8. Storing Document Paths in Database

### On Form Submit

```python
# In form submit callback (form_gen.py)
@app.callback(...)
def submit_form(form_data, document_path):
    """Save activity with document path"""
    
    # Document path returned from nextcloud integration
    # e.g., "/Reports/activity_123_20250120_143022.odt"
    
    # Add to activity record
    activity_record = {
        'name': form_data['name'],
        'description': form_data['description'],
        # ... other fields
        'tag_groups': {
            'report': {
                'nextcloud_url': '...',
                'file_path': document_path  # Store the path
            }
        }
    }
    
    # Save to database
    db.insert_activity(activity_record)
```

### Retrieving Document Path

```python
from db import get_latest_entry

# When loading activity for editing
activity_data = get_latest_entry('activities_form', forms_config, object_id=123)

document_path = activity_data.get('tag_groups', {}).get('report', {}).get('file_path')

if document_path:
    collabora_url = generate_collabora_url(
        config['nextcloud']['url'],
        document_path,
        username
    )
    print(f"Edit document: {collabora_url}")
```

## 9. Error Handling & Validation

### Pre-flight Checks

```python
def validate_nextcloud_config(config, client):
    """Validate NextCloud configuration before operations"""
    
    required_keys = ['nextcloud_url', 'folder_path', 'template_path']
    
    for key in required_keys:
        if not config.get(key):
            return False, f"Missing required config: {key}"
    
    # Check credentials are valid
    is_valid, error = client.validate_credentials()
    if not is_valid:
        return False, f"Authentication failed: {error}"
    
    # Check template exists
    if not client.check_file_exists(config['template_path']):
        return False, f"Template not found: {config['template_path']}"
    
    return True, "Configuration valid"

# Usage
valid, message = validate_nextcloud_config(tag_group_config, client)
if not valid:
    return html.Div(f"Error: {message}", style={'color': 'red'})
```

### Understanding validate_credentials()

The `validate_credentials()` method performs a WebDAV test to verify authentication:

```python
# Returns a tuple: (is_valid: bool, error_message: str)
is_valid, error_message = client.validate_credentials()

# Example responses:
# (True, "")  - Credentials are valid
# (False, "401 Unauthorized") - Invalid username/password
# (False, "Connection failed") - Network or URL issue
# (False, "Invalid response") - Server issue
```

### Retry Logic

```python
import time

def copy_file_with_retry(client, source, dest, max_retries=3):
    """Copy file with exponential backoff retry"""
    
    for attempt in range(max_retries):
        try:
            if client.copy_file(source, dest):
                return True
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
    
    return False
```

## 10. Integration with Activity Workflow

### Complete Activity Lifecycle

```python
# Step 1: Create activity with initial data
activity = {
    'id': 123,
    'name': 'Q1 Planning',
    'status': 'draft',
    'tag_groups': {}  # No documents yet
}

# Step 2: User adds Report tag group
activity['tag_groups']['report'] = {
    'nextcloud_url': 'https://nextcloud.example.com',
    'folder_path': '/Reports/2025',
    'template_path': '/Templates/planning_template.odt',
    'activity_id': 'Q1_2025'
}

# Step 3: User clicks "Create/Open Report"
# → Document created: /Reports/2025/Q1_2025_20250120_143022.odt
# → File path stored in tag_groups JSON

activity['tag_groups']['report']['file_path'] = '/Reports/2025/Q1_2025_20250120_143022.odt'

# Step 4: Activity saved to database
# The entire tag_groups JSON is stored as a single column value

# Step 5: Later, when editing activity
# → UI displays "Open in Collabora" link
# → Uses stored file_path to open document

# Step 6: User adds another document type (Meeting Minutes)
activity['tag_groups']['minutes'] = {
    'nextcloud_url': '...',
    'folder_path': '/Minutes/2025',
    'template_path': '/Templates/minutes_template.odt',
    'file_path': '/Minutes/2025/Q1_2025_minutes.odt'
}

# Step 7: Activity can have multiple collaborative documents
# All stored flexibly in JSON, no schema changes needed
```

## 11. Testing the Integration

### Unit Test Example

```python
import unittest
from unittest.mock import Mock, patch

class TestNextCloudClient(unittest.TestCase):
    
    def setUp(self):
        self.client = NextCloudClient(
            url="https://test.example.com",
            username="testuser",
            password="testpass"
        )
    
    @patch('requests.Session.request')
    def test_check_file_exists(self, mock_request):
        mock_request.return_value.status_code = 200
        
        result = self.client.check_file_exists("/test/file.odt")
        
        self.assertTrue(result)
        mock_request.assert_called_once()
    
    @patch('requests.Session.request')
    def test_validate_credentials(self, mock_request):
        mock_request.return_value.status_code = 207
        
        is_valid, error = self.client.validate_credentials()
        
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
    
    @patch('requests.Session.request')
    def test_validate_credentials_failure(self, mock_request):
        mock_request.return_value.status_code = 401
        
        is_valid, error = self.client.validate_credentials()
        
        self.assertFalse(is_valid)
        self.assertIn("401", error)
    
    @patch('requests.Session.request')
    def test_copy_file(self, mock_request):
        mock_request.return_value.status_code = 201
        
        result = self.client.copy_file("/source.odt", "/dest.odt")
        
        self.assertTrue(result)
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], 'COPY')
        self.assertIn('Destination', call_args[1]['headers'])
```

### Integration Test

```python
# Manual testing with real NextCloud instance
def test_full_workflow():
    # Initialize
    client = NextCloudClient(
        url=os.environ.get('TEST_NEXTCLOUD_URL'),
        username=os.environ.get('TEST_NEXTCLOUD_USER'),
        password=os.environ.get('TEST_NEXTCLOUD_PASSWORD')
    )
    
    # Test credentials
    is_valid, error = client.validate_credentials()
    assert is_valid, f"Credentials invalid: {error}"
    
    # Test operations
    assert client.create_folder("/test_reports")
    assert client.check_file_exists("/Templates/template.odt")
    assert client.copy_file(
        "/Templates/template.odt",
        "/test_reports/test_doc.odt"
    )
    assert client.check_file_exists("/test_reports/test_doc.odt")
    
    print("✓ All tests passed")
```

## 12. Performance Optimization

### Caching Template Existence

```python
from functools import lru_cache
import time

class CachedNextCloudClient(NextCloudClient):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._file_cache = {}
        self._cache_timeout = 3600  # 1 hour
    
    def check_file_exists(self, remote_path):
        """Check with simple caching"""
        cache_key = remote_path
        
        if cache_key in self._file_cache:
            cached_time, cached_result = self._file_cache[cache_key]
            if time.time() - cached_time < self._cache_timeout:
                return cached_result
        
        result = super().check_file_exists(remote_path)
        self._file_cache[cache_key] = (time.time(), result)
        return result
```

### Batch Operations

```python
def copy_multiple_files(client, file_pairs):
    """Copy multiple files in sequence with error handling"""
    
    results = []
    for source, dest in file_pairs:
        try:
            success = client.copy_file(source, dest)
            results.append({
                'source': source,
                'dest': dest,
                'success': success
            })
        except Exception as e:
            results.append({
                'source': source,
                'dest': dest,
                'success': False,
                'error': str(e)
            })
    
    return results
```

These examples demonstrate various aspects of integrating NextCloud and Collabora Online with Collaboratorium.
