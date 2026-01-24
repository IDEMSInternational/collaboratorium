# NextCloud & Collabora Online Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     User's Web Browser                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ├─ HTTPS/TLS
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    Nginx Reverse Proxy                           │
│  (SSL termination, routing, security headers)                   │
└─┬──────────────┬──────────────┬──────────────┬──────────────────┘
  │              │              │              │
  │ /            │ /nextcloud   │ /collabora   │
  │              │              │              │
  ▼              ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Dashed    │  │NextCloud │  │Collabora │  │  (More)  │
│App       │  │FPM+      │  │Online    │  │Services  │
│(Port     │  │WebDAV    │  │(Port     │  │          │
│8050)     │  │(Port 9000)  │9980)    │  │          │
└──────────┘  └────┬─────┘  └──────────┘  └──────────┘
     │             │
     │             ▼
     │        ┌──────────────┐
     │        │  MariaDB     │
     │        │ (NextCloud   │
     │        │  Database)   │
     │        │  (Port 3306) │
     │        └──────────────┘
     │
     │ (OAuth, form management,
     │  document control)
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│           Collaboratorium Dash Application                       │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ component_factory.py                                        │ │
│  │  - Generates "nextcloud_doc" element type                  │ │
│  │  - Creates button, store, status div                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│  │                                                               │
│  ├─ next cloud_integration.py                                   │
│  │  ┌──────────────────────────────────────────────────────┐  │
│  │  │ NextCloudClient (WebDAV)                             │  │
│  │  │ ├─ check_file_exists() [PROPFIND]                   │  │
│  │  │ ├─ copy_file() [COPY]                               │  │
│  │  │ ├─ create_folder() [MKCOL]                          │  │
│  │  │ └─ validate_credentials() [Test auth]               │  │
│  │  │                                                      │  │
│  │  │ register_nextcloud_callbacks()                       │  │
│  │  │ ├─ Handles nextcloud_doc button clicks              │  │
│  │  │ ├─ Handles nextcloud_attachments button clicks      │  │
│  │  │ └─ Smart element ID matching for table updates      │  │
│  │  │                                                      │  │
│  │  │ register_nextcloud_password_callback()              │  │
│  │  │ └─ Manages password input & session storage         │  │
│  │  └──────────────────────────────────────────────────────┘  │
│  │                                                               │
│  └─ form_gen.py                                                 │
│     ├─ Registers callbacks, manages form flow                  │
│     └─ Reads DataTable.data property for table persistence     │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ config.yaml                                                 │ │
│  │  - NextCloud URL configuration                              │ │
│  │  - Default folders & template paths                         │ │
│  │  - Institutional customization via subforms (tag_groups)    │ │
│  │  - NextCloud password input component definition            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Database (SQLite)                                           │ │
│  │  - tag_groups table (flexible JSON configuration)           │ │
│  │  - activities/initiatives/... (with tag_groups column)     │ │
│  │  - Stores document paths and metadata                      │ │
│  │  - Table data for nextcloud_attachments components         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Flask Session Management                                   │ │
│  │  - Stores NextCloud password for session duration          │ │
│  │  - Used by callbacks for authentication                    │ │
│  │  - No persistent storage of sensitive credentials          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
User clicks "Create/Open Report"
    │
    ▼
┌─────────────────────────────────────────┐
│ handle_nextcloud_document_creation()    │
│ (JavaScript/Python callback)            │
└──────┬──────────────────────────────────┘
       │
       ├─ Extract config from dcc.Store
       │  (nextcloud_url, folder_path, template_path, activity_id)
       │
       ├─ Get user credentials
       │  (Email from Google OAuth → username)
       │  (NEXTCLOUD_APP_PASSWORD from env)
       │
       ▼
┌─────────────────────────────────────────┐
│ NextCloudClient initialization          │
│ (requests.Session with HTTP Basic Auth) │
└──────┬──────────────────────────────────┘
       │
       ├─ PROPFIND /remote.php/dav/files/username/Reports/
       │  (Check if folder exists)
       │
       ├─ MKCOL (if needed)
       │  (Create folder structure)
       │
       ├─ Generate filename: activity_123_20250120_143022.odt
       │
       ├─ PROPFIND (Check if document exists)
       │
       ├─ If not exists: COPY /Templates/report_template.odt
       │              to /Reports/activity_123_20250120_143022.odt
       │
       ▼
┌─────────────────────────────────────────┐
│ Generate Collabora URL                  │
│ /index.php/apps/richdocuments/files/... │
└──────┬──────────────────────────────────┘
       │
       ├─ Return to UI:
       │  - Success message (green)
       │  - Clickable link to Collabora
       │  - Update hidden file path input
       │
       ▼
┌─────────────────────────────────────────┐
│ Store values in Dash components:        │
│ - nextcloud_output: Success message     │
│ - nextcloud_file_path: "/Reports/..."   │
│ - nextcloud_config: Updated config      │
└──────┬──────────────────────────────────┘
       │
       └─ User clicks link to Collabora
          │
          ▼
          Collabora Online opens document in iframe
          (Real-time collaborative editing)
          │
          └─> Auto-save to NextCloud
```

## Element ID Matching for Nested Components

When using `nextcloud_attachments` within subforms, the callback must identify which table to update. This uses intelligent element ID matching:

```
Form Structure (YAML):
┌─────────────────────────────────────┐
│ form_name                           │
│  ├─ regular_input (element type)    │
│  ├─ subform_id (subform type)       │  ← Contains nested elements
│  │  ├─ nested_input (inside subform)│
│  │  ├─ nextcloud_attachments        │  ← Target component
│  │  │   button ID: {type: "nextcloud_button", form: "form_name|subform_id", element: "nextcloud_attachments"}
│  │  └─ other_element                │
│  └─ another_input                   │
└─────────────────────────────────────┘

Callback Logic:
1. Button clicked: {type: "nextcloud_button", form: "form_name|subform_id", element: "nextcloud_attachments"}
2. Extract element: "nextcloud_attachments"
3. Search input_ids list for matching element
4. Find table with matching element ID
5. Update ONLY that table with new row
6. Return updated DataTable.data

Key Benefit:
- Multiple attachment tables in single form don't interfere
- Correct document added to correct table automatically
- Subform nesting fully supported
```

Example:

```python
# Form config has this structure:
# activities_form
#   └─ attachments (nextcloud_attachments)
#        button ID: {type: "nextcloud_button", form: "activities_form", element: "attachments"}

# Callback receives trigger:
@app.callback(
    Output(...), 
    Input({"type": "nextcloud_button", "form": ALL, "element": ALL}, "n_clicks"),
    State(...),
    prevent_initial_call=True
)
def handle_creation(n_clicks, triggered_id, ...):
    if not triggered_id:
        return
    
    button_id = json.loads(triggered_id)
    button_element = button_id.get('element')  # "attachments"
    
    # Find matching table in input_ids
    for input_id in input_ids:
        if input_id.get('element') == button_element:
            # This is our table - update it
            table_data = [...new row...]
            return table_data
```

## Password Input and Session Management

The password callback manages NextCloud authentication:

```
User Flow:
1. User opens Collaboratorium app
2. Main panel shows "NextCloud Password" section
3. User enters app password from NextCloud
4. Clicks "Save Password" button
5. Callback validates and stores in session['nextcloud_password']
6. Status message shows success
7. Password available to nextcloud_integration callbacks
8. Password cleared when user logs out or session expires

Callback Implementation:
┌────────────────────────────────────────┐
│ register_nextcloud_password_callback()  │
├────────────────────────────────────────┤
│                                         │
│ Input: Password text input n_submit     │
│                                         │
│ Process:                                │
│ 1. Check if password is provided        │
│ 2. Store in session['nextcloud_password']
│ 3. Return success/error message        │
│                                         │
│ Output: nextcloud_password_output div   │
│         (HTML with status message)      │
│                                         │
└────────────────────────────────────────┘

Security Notes:
- Password only stored in Flask session
- Not persisted to database
- Transmitted over HTTPS only
- Cleared on logout
- Used only by server-side WebDAV client
- Never exposed to client-side JavaScript
```

## Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      Activity Form                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Tag Group Selector (Subform)                               │  │
│  │                                                             │  │
│  │  [Dropdown: Report ▼] [Add Subform]                       │  │
│  │                                                             │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │ Report Subform (JSON Storage)                        │ │  │
│  │  │                                                       │ │  │
│  │  │ [NextCloud URL: ...................]                │ │  │
│  │  │ [Folder Path: /Reports ...........]                │ │  │
│  │  │ [Template Path: /Templates/......]                │ │  │
│  │  │ [Document ID: activity_123 ......]                │ │  │
│  │  │                                                       │ │  │
│  │  │ [Create/Open Report]  ← Button (nextcloud_button)   │ │  │
│  │  │                                                       │ │  │
│  │  │ ┌─────────────────────────────────────────────────┐ │ │  │
│  │  │ │ ✓ Document created successfully!               │ │ │  │
│  │  │ │ [Open in Collabora Online] ← Link              │ │ │  │
│  │  │ └─────────────────────────────────────────────────┘ │ │  │
│  │  │ (nextcloud_output div)                              │ │  │
│  │  │                                                       │ │  │
│  │  │ ┌─────────────────────────────────────────────────┐ │ │  │
│  │  │ │ Supporting Documents (nextcloud_attachments)   │ │ │  │
│  │  │ │ [Create New Document] ← Button                 │ │ │  │
│  │  │ │                                                  │ │ │  │
│  │  │ │ ┌────────────────────────────────────────────┐ │ │ │  │
│  │  │ │ │ Filename        │ Editor Link            │ │ │ │  │
│  │  │ │ ├────────────────────────────────────────────┤ │ │ │  │
│  │  │ │ │ report_20250120│ [Open in Collabora] [X] │ │ │ │  │
│  │  │ │ │ summary_20250.│ [Open in Collabora] [X] │ │ │ │  │
│  │  │ │ └────────────────────────────────────────────┘ │ │ │  │
│  │  │ │ (DataTable - auto-updated when docs created)   │ │ │  │
│  │  │ └─────────────────────────────────────────────────┘ │ │  │
│  │  │                                                       │ │  │
│  │  │ <hidden>                                              │ │  │
│  │  │ nextcloud_config (dcc.Store): {config...}            │ │  │
│  │  │ nextcloud_file_path (dcc.Input): /Reports/...       │ │  │
│  │  │ </hidden>                                             │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  [Submit] [Cancel]                                               │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
         │
         └─ On form submit, entire tag_groups JSON stored in DB
            as single column value
```

## Database Schema (Simplified)

```
activities table:
┌─────────┬─────────┬─────────┬─────────────────┬──────────────┐
│ id      │ name    │ ...     │ tag_groups      │ ...          │
├─────────┼─────────┼─────────┼─────────────────┼──────────────┤
│ 1       │ Act 1   │ ...     │ {"1": {...}}    │ ...          │
│ 2       │ Act 2   │ ...     │ {"1": {...}}    │ ...          │
│ 3       │ Act 3   │ ...     │ {}              │ ...          │
└─────────┴─────────┴─────────┴─────────────────┴──────────────┘

tag_groups table:
┌─────────┬─────────────┬──────────────────────────────────────┐
│ id      │ name        │ key_values                           │
├─────────┼─────────────┼──────────────────────────────────────┤
│ 1       │ Report      │ {                                    │
│         │             │   "nextcloud_url": {...},          │
│         │             │   "folder_path": {...},            │
│         │             │   "template_path": {...},          │
│         │             │   "activity_id": {...}             │
│         │             │ }                                    │
└─────────┴─────────────┴──────────────────────────────────────┘

Key benefit: Flexible configuration without schema changes
            Multiple tag groups can have different structures
            Institutional customization via configuration
```

## Security Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     HTTPS/TLS Layer                            │
│           (Nginx terminates SSL/TLS certificates)             │
└───────────────┬───────────────────────────────────────────────┘
                │
    ┌───────────┴──────────────┬──────────────────┐
    │                          │                  │
    ▼                          ▼                  ▼
┌─────────┐            ┌──────────┐         ┌──────────┐
│Dash App │            │NextCloud │         │Collabora │
│         │            │          │         │          │
│Auth:    │            │Auth:     │         │Auth:     │
│Google   │            │WebDAV    │         │NextCloud │
│OAuth    │            │(HTTP     │         │Session   │
│         │            │Basic)    │         │          │
└─────────┘            └──────────┘         └──────────┘
    │                       │
    │ Email prefix          │ App Password
    │ (user@org.com→user)   │ (environment variable)
    │                       │
    └───────────┬───────────┘
                │
                ▼
          ┌──────────────┐
          │ NextCloud DB │
          │   (MariaDB)  │
          │              │
          │ Credentials  │
          │ stored       │
          │ encrypted    │
          └──────────────┘

Security notes:
1. OAuth ensures only authenticated Collaboratorium users can access
2. WebDAV auth uses app password, not user password
3. All traffic encrypted over HTTPS via nginx
4. File paths generated with timestamp to prevent conflicts
5. User folders isolated (/admin/, /user@org/, etc.)
```

## Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                    Internet / LAN                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                    HTTPS (port 443)
                         │
        ┌────────────────▼─────────────────┐
        │   Nginx (Reverse Proxy)          │
        │   - Domain: example.com          │
        │   - SSL/TLS termination          │
        │   - Rate limiting                │
        │   - Security headers             │
        └────┬───────┬───────┬─────────────┘
             │       │       │
    ┌────────┘       │       └──────────┐
    │                │                  │
    ▼                ▼                  ▼
┌─────────┐    ┌──────────┐    ┌───────────────┐
│Collab-  │    │NextCloud │    │Collabora      │
│atorium │    │          │    │Online         │
│ Dash    │    │ - FPM    │    │               │
│         │    │ - WebDAV │    │ - Document    │
│ Port    │    │          │    │   editor      │
│ 8050    │    │ Port 9000│    │               │
│         │    │          │    │ Port 9980     │
└────┬────┘    └────┬─────┘    └───────────────┘
     │              │
     │              └─────────┬──────────┐
     │                        │          │
     │                        ▼          ▼
     │                    ┌────────┐  ┌───────┐
     │                    │MariaDB │  │Volume:│
     │                    │        │  │Data,  │
     │                    │ Port   │  │Config │
     │                    │ 3306   │  │       │
     │                    └────────┘  └───────┘
     │
     └─────────────────┬─────────────────────┐
                       │                     │
                       ▼                     ▼
                   ┌────────┐           ┌─────────┐
                   │SQLite  │           │Analytics│
                   │Database│           │Database │
                   │ (local)│           │ (local) │
                   └────────┘           └─────────┘

Containerization: docker-compose
- One container per service
- Isolated networks
- Volume persistence
- Environment variable configuration
```

## Request Flow: Create Report

```
1. User UI Event:
   └─ Click "Create/Open Report" button
      │
      ├─ Dash callback triggered
      ├─ Component ID: {"type": "nextcloud_button", "form": "...", "element": "..."}
      └─ Event: n_clicks incremented

2. Callback Execution:
   └─ handle_nextcloud_document_creation()
      │
      ├─ Extract config from dcc.Store (tag group parameters)
      ├─ Extract user from Flask session (Google OAuth)
      ├─ Get app password from environment
      │
      └─ Validate all required parameters

3. NextCloud Operations:
   └─ Initialize NextCloudClient
      │
      ├─ WebDAV PROPFIND: Check folder exists
      │  └─ If not: MKCOL to create
      │
      ├─ Generate filename: {activity_id}_{timestamp}.odt
      │
      ├─ WebDAV PROPFIND: Check document exists
      │  └─ If not: COPY from template
      │
      └─ WebDAV operations over HTTPS with Basic Auth

4. URL Generation:
   └─ generate_collabora_url()
      │
      ├─ Encode file path
      ├─ Build Collabora iframe URL
      │
      └─ Format: /index.php/apps/richdocuments/files/{username}/{filepath}

5. Response to UI:
   └─ Update three components:
      │
      ├─ nextcloud_output: HTML with success message & link
      ├─ nextcloud_file_path: Store document path for database
      ├─ nextcloud_config: Updated config (optional)
      │
      └─ Display link to user

6. User Interaction:
   └─ Click link → Opens Collabora in iframe/new tab
      │
      ├─ Collabora establishes WebSocket with NextCloud
      ├─ Document loaded
      ├─ Real-time collaboration enabled
      │
      └─ Auto-save to NextCloud on changes
```

This architecture provides scalability, security, and flexibility for institutional document collaboration.
