"""
NextCloud and Collabora Online integration for Collaboratorium.

Handles document creation and collaboration via WebDAV and Collabora endpoints.
Documents are stored as JSON in tag_groups for easy institutional customization.
"""

import os
import json
import requests
from urllib.parse import quote
from datetime import datetime
from dash import Input, Output, State, ctx, html, no_update, ALL
from flask import session
import xml.etree.ElementTree as ET


class NextCloudClient:
    """Minimal WebDAV client for NextCloud operations."""
    
    def __init__(self, url, username, password, verify_ssl=True, group_folder=True):
        """
        Initialize NextCloud client.
        
        Args:
            url: NextCloud base URL (e.g., 'https://nextcloud.example.com')
            username: NextCloud username
            password: NextCloud app password or password
            group_folder: Whether to use group folder
        """
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.group_folder = group_folder
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.auth = (username, password)
    
    def _get_webdav_base_path(self):
        """Get the base WebDAV path."""
        return f"{self.url}/remote.php/dav/files/{quote(self.username)}"
    
    def validate_credentials(self):
        """
        Validate NextCloud credentials by attempting a simple WebDAV request.
        
        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        try:
            resp = self.session.request('GET', self.url, timeout=5)
            
            if resp.status_code in (200, 207):
                return True, None
            elif resp.status_code == 401:
                return False, "Invalid NextCloud credentials (username or password incorrect)"
            elif resp.status_code == 404:
                return False, "NextCloud URL not found or invalid"
            else:
                return False, f"NextCloud connection error: HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Could not connect to NextCloud. Check the URL and network connectivity."
        except requests.exceptions.Timeout:
            return False, "NextCloud request timed out. Server may be unavailable."
        except requests.RequestException as e:
            return False, f"NextCloud connection error: {str(e)}"
    
    def check_file_exists(self, remote_path):
        """Check if a file exists at the given remote path."""
        webdav_base = self._get_webdav_base_path()
        webdav=f"{webdav_base}/{quote(remote_path.lstrip('/'))}"
        try:
            resp = self.session.request('PROPFIND', webdav, timeout=5)
            return resp.status_code in (200, 207)
        except requests.RequestException:
            return False
    
    def copy_file(self, source_path, dest_path):
        """Copy a file from source to destination using WebDAV."""
        webdav_base = self._get_webdav_base_path()
        source_webdav = f"{webdav_base}/{quote(source_path.lstrip('/'))}"
        dest_webdav = f"{webdav_base}/{quote(dest_path.lstrip('/'))}"
        
        try:
            resp = self.session.request(
                'COPY',
                source_webdav,
                headers={'Destination': dest_webdav},
                timeout=10
            )
            return resp.status_code in (200, 201, 204)
        except requests.RequestException as e:
            print(f"Error copying file: {e}")
            return False
    
    def create_folder(self, folder_path):
        """Create a folder (and parent folders) via WebDAV MKCOL."""
        folder_path = folder_path.lstrip('/').rstrip('/')
        parts = folder_path.split('/')
        
        webdav_base = self._get_webdav_base_path()
        for i in range(1, len(parts) + 1):
            current_path = '/'.join(parts[:i])
            webdav_url = f"{webdav_base}/{quote(current_path)}"
            
            if not self.check_file_exists(current_path):
                try:
                    resp = self.session.request('MKCOL', webdav_url, timeout=5)
                    if resp.status_code not in (200, 201, 204, 405):  # 405 = already exists
                        return False
                except requests.RequestException:
                    return False
        
        return True

    def get_file_id(self, remote_path):
        """Fetch NextCloud's internal file ID (e.g., for /f/123 links)."""
        webdav_base = self._get_webdav_base_path()
        webdav = f"{webdav_base}/{quote(remote_path.lstrip('/'))}"
        headers = {'Depth': '0', 'Content-Type': 'application/xml'}
        
        # Explicitly request the oc:id property via WebDAV
        body = '''<?xml version="1.0"?>
        <d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
            <d:prop>
                <oc:id />
            </d:prop>
        </d:propfind>'''
        
        try:
            resp = self.session.request('PROPFIND', webdav, headers=headers, data=body, timeout=5)
            if resp.status_code in (200, 207):
                root = ET.fromstring(resp.content)
                # Parse the oc:id from the XML namespace
                namespaces = {'d': 'DAV:', 'oc': 'http://owncloud.org/ns'}
                file_id_elem = root.find('.//oc:id', namespaces)
                
                if file_id_elem is not None and file_id_elem.text:
                    return file_id_elem.text
        except Exception as e:
            print(f"Error fetching file ID: {e}")
            
        return None


def generate_collabora_url(nextcloud_url, file_path, username, group_folder=True, file_id=None):
    """
    Generate a Collabora Online editing URL for a document in NextCloud.
    Modern NextCloud uses /f/{file_id} to route automatically.
    """
    nextcloud_url = nextcloud_url.rstrip('/')
    
    # Use the reliable /f/file_id route if we successfully fetched it
    if file_id:
        return f"{nextcloud_url}/f/{file_id}"
        
    # ... keep the rest of the old function as a fallback ...
    file_path = file_path.lstrip('/')
    
    # Encode the file path for use in the Collabora URL
    if group_folder:
        encoded_path = quote(f"{file_path}")
    else:
        encoded_path = quote(f"{username}/{file_path}")
    
    collabora_url = (
        f"{nextcloud_url}/index.php/apps/richdocuments/files/{encoded_path}"
    )
    return collabora_url


def register_nextcloud_callbacks(app, config):
    """
    Register callbacks for NextCloud document operations.
    
    Expects config to contain:
    {
        'nextcloud': {
            'url': 'https://nextcloud.example.com',
            'default_folder': '/Reports',
            'default_template': '/Templates/report_template.odt',
            'group_folder': True  # Optional: whether to use group folder instead of user folder
        }
    }
    """
    nextcloud_config = config.get('nextcloud', {})
    
    if not nextcloud_config.get('url'):
        print("WARNING: NextCloud integration disabled (no URL in config)")
        return

    @app.callback(
        Output({"type": "nextcloud_output", "form": ALL, "element": ALL}, "children"),
        Output({"type": "nextcloud_file_path", "form": ALL, "element": ALL}, "value"),
        Output({"type": "input", "form": ALL, "element": ALL}, "data", allow_duplicate=True),
        Input({"type": "nextcloud_button", "form": ALL, "element": ALL}, "n_clicks"),
        State({"type": "nextcloud_config", "form": ALL, "element": ALL}, "data"),
        State({"type": "nextcloud_file_path", "form": ALL, "element": ALL}, "value"),
        State({"type": "input", "form": ALL, "element": ALL}, "id"),
        State({"type": "input", "form": ALL, "element": ALL}, "data"),
        State({"type": "input", "form": ALL, "element": ALL}, "value"),
        prevent_initial_call=True,
    )
    def handle_nextcloud_document_creation(n_clicks_list, configs, current_paths, input_ids, table_data_list, input_values):
        """
        Handle document creation/opening on NextCloud.
        
        Flow:
        1. Extract configuration from tag group (stored in Store)
        2. Initialize NextCloud client with credentials
        3. Check if document exists; if not, copy template
        4. Generate Collabora Online link
        5. Automatically add document URL to attachments table (matched by element ID)
        6. Return link, file path, and updated table data
        """
        if not ctx.triggered or not any(n_clicks_list):
            return [no_update] * len(n_clicks_list), [no_update] * len(n_clicks_list), [no_update] * len(table_data_list)
        
        # Identify which button was clicked
        trigger = ctx.triggered[0]
        trigger_id = trigger['prop_id'].split('.')[0]
        
        try:
            trigger_obj = json.loads(trigger_id)
            form_name = trigger_obj.get('form')
            button_element = trigger_obj.get('element')
            idx = next(i for i, nc in enumerate(n_clicks_list) if nc)
        except (json.JSONDecodeError, StopIteration):
            return [no_update] * len(n_clicks_list), [no_update] * len(n_clicks_list), [no_update] * len(table_data_list)
        
        config = configs[idx] if idx < len(configs) else {}
        current_path = current_paths[idx] if idx < len(current_paths) else None
        
        # Extract object ID from the form's hidden 'id' field
        object_id = "new"
        if input_ids:
            for i, input_id in enumerate(input_ids):
                if isinstance(input_id, dict) and input_id.get('element') == 'id':
                    if i < len(input_values) and input_values[i]:
                        object_id = str(input_values[i])
                    break
                    
        # Extract base table name from form_name (e.g., 'activities_form-description' -> 'activities')
        base_table = form_name.split('-')[0].replace('_form', '') if form_name else 'document'

        # Initialize output lists
        outputs_children = [no_update] * len(n_clicks_list)  # type: ignore
        outputs_paths = [no_update] * len(n_clicks_list)  # type: ignore
        outputs_tables = [no_update] * len(table_data_list)  # type: ignore
        
        # Find the matching table by element ID (for subforms, extract the subform_id|element_id pattern)
        table_idx = None
        if input_ids:
            for i, input_id in enumerate(input_ids):
                if isinstance(input_id, dict) and input_id.get('element') == button_element:
                    table_idx = i
                    break
        
        try:
            # Extract NextCloud settings from the tag group configuration
            nc_url = config.get('nextcloud_url') or nextcloud_config.get('url')
            nc_verify_ssl = nextcloud_config.get('verify_ssl', True)
            nc_username = session.get('user', {}).get('email', '').split('@')[0]  # Use email prefix
            nc_group_folder = nextcloud_config.get('group_folder')
            
            # Try to get password from session first, then environment, then config
            nc_password = session.get('nextcloud_password') or os.environ.get('NEXTCLOUD_APP_PASSWORD', nextcloud_config.get('app_password'))
            
            folder_path = config.get('folder_path') or nextcloud_config.get('default_folder', '/Reports')
            template_path = config.get('template_path') or nextcloud_config.get('default_template', '/Templates/report_template.odt')
            activity_id = config.get('activity_id', 'document')
            
            if not all([nc_url, nc_username, nc_password]):
                error_html = html.Div([
                    html.P("Error: NextCloud credentials not configured.", style={'color': 'red'}),
                    html.P("Contact administrator to set NEXTCLOUD_APP_PASSWORD environment variable.")
                ], style={'color': 'red'})
                outputs_children[idx] = error_html  # type: ignore
                return outputs_children, outputs_paths, outputs_tables
            
            # Initialize client and validate credentials
            client = NextCloudClient(nc_url, nc_username, nc_password, verify_ssl=nc_verify_ssl, group_folder=nc_group_folder)
            is_valid, error_msg = client.validate_credentials()
            
            if not is_valid:
                error_html = html.Div([
                    html.P(f"Error: {error_msg}", style={'color': 'red'}),
                    html.P(f"Please verify NextCloud URL ({nc_url}) and credentials are correct.")
                ], style={'color': 'red'})
                outputs_children[idx] = error_html  # type: ignore
                return outputs_children, outputs_paths, outputs_tables
            
            # Create folder structure if needed
            if not client.create_folder(folder_path):
                error_html = html.Div([
                    html.P("Error: Could not create folder in NextCloud.", style={'color': 'red'})
                ], style={'color': 'red'})
                outputs_children[idx] = error_html  # type: ignore
                return outputs_children, outputs_paths, outputs_tables
            
            # Generate file path
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            prefix = config.get('activity_id') or base_table
            file_name = f"{prefix}_{object_id}_{timestamp}.odt"
            file_path = f"{folder_path.rstrip('/')}/{file_name}"
            
            # Check if document exists; create from template if not
            if not client.check_file_exists(file_path):
                if not client.copy_file(template_path, file_path):
                    error_html = html.Div([
                        html.P("Error: Could not copy template to NextCloud.", style={'color': 'red'})
                    ], style={'color': 'red'})
                    outputs_children[idx] = error_html  # type: ignore
                    return outputs_children, outputs_paths, outputs_tables
            
            # Fetch the internal file ID for the new (or existing) document
            file_id = client.get_file_id(file_path)
            
            # Generate Collabora URL
            collabora_url = generate_collabora_url(nc_url, file_path, nc_username, group_folder=nc_group_folder, file_id=file_id)
            
            # Automatically add document to attachments table using the matched table_idx
            if table_idx is not None and table_idx < len(table_data_list) and table_data_list[table_idx]:
                table_data = list(table_data_list[table_idx])
                new_row = {
                    'name': file_name.replace('.odt', '').replace('_', ' '),
                    'url': collabora_url,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                table_data.insert(0, new_row)  # Add to beginning (most recent first)
                outputs_tables[table_idx] = table_data  # type: ignore
            
            # Return success message with clickable link
            output_html = html.Div([
                html.P("Document created successfully!", style={'color': 'green'}),
                html.A(
                    "Open in Collabora Online",
                    href=collabora_url,
                    target="_blank",
                    style={
                        'display': 'inline-block',
                        'padding': '10px 15px',
                        'backgroundColor': '#4CAF50',
                        'color': 'white',
                        'textDecoration': 'none',
                        'borderRadius': '4px',
                        'marginTop': '10px'
                    }
                )
            ])
            
            outputs_children[idx] = output_html  # type: ignore
            outputs_paths[idx] = file_path  # type: ignore
            
            return outputs_children, outputs_paths, outputs_tables
        
        except Exception as e:
            print(f"NextCloud integration error: {e}")
            error_output = html.Div([
                html.P(f"Error: {str(e)}", style={'color': 'red'})
            ], style={'color': 'red'})
            
            outputs_children[idx] = error_output  # type: ignore
            
            return outputs_children, outputs_paths, outputs_tables

    @app.callback(
        Output("collabora-modal", "is_open"),
        Output("collabora-iframe", "src"),
        Output("modal-new-tab-link", "href"), # <-- Pass the URL to the modal's "pop-out" button
        Input({"type": "open-doc-btn", "url": ALL}, "n_clicks"),
        Input("close-collabora-modal", "n_clicks"),
        State("collabora-modal", "is_open"),
        prevent_initial_call=True
    )
    def toggle_collabora_modal(open_clicks, close_clicks, is_open):
        if not ctx.triggered:
            return no_update, no_update, no_update
            
        # ctx.triggered_id automatically returns a dict for pattern-matching IDs, or a string for standard IDs!
        trigger_id = ctx.triggered_id
        
        # If the user clicked the Close button
        if trigger_id == "close-collabora-modal":
            return False, "", "" 
            
        # If the user clicked a document link
        if isinstance(trigger_id, dict) and trigger_id.get("type") == "open-doc-btn":
            # Ensure it was an actual click
            idx = next((i for i, nc in enumerate(open_clicks) if nc), None)
            if idx is not None and open_clicks[idx] > 0:
                document_url = trigger_id.get("url")
                # Return: Open Modal, Set Iframe SRC, Set Pop-out href
                return True, document_url, document_url
                
        return no_update, no_update, no_update


def register_nextcloud_password_callback(app):
    """
    Register callback to handle NextCloud password input and validation.
    
    Stores the password in the Flask session for the duration of the user's login.
    Password can be provided via:
    1. A password input component with id "nextcloud_password_input"
    2. Environment variable NEXTCLOUD_APP_PASSWORD
    3. Will prompt user if not provided
    """
    @app.callback(
        Output("nextcloud_password_status", "children"),
        Input("nextcloud_password_input", "value"),
        Input("nextcloud_validate_button", "n_clicks"),
        State("nextcloud_password_input", "value"),
        prevent_initial_call=True,
    )
    def handle_password_input(input_value, n_clicks, password):
        """Store and validate NextCloud password."""
        if not password:
            return html.Div("Please enter a NextCloud password.", style={'color': 'orange'})
        
        # Store in session
        session['nextcloud_password'] = password
        
        return html.Div(
            "✓ NextCloud password stored in session.",
            style={'color': 'green'}
        )


def register_nextcloud_tag_group(app):
    """
    Register a convenience callback to extract NextCloud config from tag groups.
    
    This allows dynamic forms to populate NextCloud settings from the tag group data.
    """
    @app.callback(
        Output({"type": "nextcloud_config", "form": ALL}, "data"),
        Input({"type": "input", "form": ALL, "element": ALL}, "value"),
        State({"type": "nextcloud_config", "form": ALL}, "id"),
        prevent_initial_call=True,
    )
    def update_nextcloud_config(values, config_ids):
        """
        Update NextCloud config when tag group fields change.
        
        Maps form field values to NextCloud configuration parameters.
        """
        if not ctx.triggered or not config_ids:
            return [no_update] * len(config_ids)
        
        # This is handled by the parent tag group callback
        # This is just a placeholder for future enhancements
        return [no_update] * len(config_ids)
