import os
import sqlite3
import secrets
import tempfile
import shutil
from flask import send_file, request, abort, render_template_string, session, after_this_request
from auth import login_required

ADMIN_EMAILS = [email.strip() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()]

def register_admin_routes(server):
    
    @server.route('/admin/maintenance', methods=['GET', 'POST'])
    @login_required
    def admin_maintenance():
        user = session.get("user")
        
        if not user or user.get("email") not in ADMIN_EMAILS:
            abort(403, description="Unauthorized: You do not have admin privileges.")

        db_path = os.path.abspath("database.db")

        # Ensure CSRF token exists in the session
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(16)

        # Handle POST (Upload/Restore)
        if request.method == 'POST':
            # CSRF Validation
            token = session.pop('csrf_token', None)
            if not token or token != request.form.get('csrf_token'):
                abort(400, description="CSRF token missing or invalid.")

            if 'db_file' not in request.files:
                return "No file uploaded.", 400
                
            file = request.files['db_file']
            if file.filename == '' or not file.filename.endswith('.db'):
                return "Invalid file type. Please upload a .db file.", 400
            
            # Save to a temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            file.save(temp_path)

            try:
                # Validate the uploaded SQLite file
                conn = sqlite3.connect(temp_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()
                conn.close()

                if not result or result[0].lower() != 'ok':
                    os.remove(temp_path)
                    return "Database validation failed. The file is corrupt or not a valid SQLite database.", 400

                # Safe replacement (shutil.copy2 preserves permissions and avoids breaking Docker bind mounts)
                shutil.copy2(temp_path, db_path)
                os.remove(temp_path)

                return """
                    <div style="font-family: sans-serif; margin: 40px;">
                        <h2 style="color: green;">✅ Database restored and validated successfully!</h2>
                        <a href="/">Return to Dashboard</a>
                    </div>
                """
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return f"An error occurred during validation: {str(e)}", 500

        # Handle GET (Download/Backup)
        if request.args.get('action') == 'download':
            if not os.path.exists(db_path):
                abort(404, description="Database file not found.")
            
            # Create a safe snapshot using VACUUM INTO
            fd, snapshot_path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            
            try:
                # Connect to the live DB and export to the snapshot path
                # VACUUM INTO safely handles concurrent writes
                with sqlite3.connect(db_path) as conn:
                    # Remove the snapshot file first, as VACUUM INTO requires the target to not exist
                    os.remove(snapshot_path) 
                    conn.execute(f"VACUUM INTO '{snapshot_path}'")
                
                # Cleanup the snapshot after sending
                @after_this_request
                def remove_file(response):
                    try:
                        os.remove(snapshot_path)
                    except Exception:
                        pass
                    return response

                return send_file(snapshot_path, as_attachment=True, download_name="collaboratorium_backup.db")
            except Exception as e:
                if os.path.exists(snapshot_path):
                    os.remove(snapshot_path)
                abort(500, description=f"Failed to create database snapshot: {str(e)}")

        # Serve the Admin UI (Injected with CSRF Token)
        html_template = """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>Admin Maintenance</title>
          <style>
            body { font-family: "Segoe UI", sans-serif; margin: 40px; background: #f4f6f8; color: #212529; }
            .card { background: #fff; padding: 25px; border-radius: 8px; border: 1px solid #dee2e6; max-width: 500px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            .btn { background: #f28b20; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: bold; }
            .btn:hover { background: #d97b1a; }
            .danger { background: #dc3545; }
            .danger:hover { background: #c82333; }
            hr { border: 0; border-top: 1px solid #dee2e6; margin: 20px 0; }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>System Maintenance</h2>
            <p>Logged in as: <strong>{{ email }}</strong></p>
            <hr>
            
            <h3>1. Backup Database</h3>
            <p>Download a consistent snapshot of the live SQLite database.</p>
            <a href="/admin/maintenance?action=download" class="btn">Download database.db</a>
            
            <hr>
            
            <h3>2. Restore Database</h3>
            <p style="color: #dc3545;"><strong>Warning:</strong> This will overwrite the live database (validated via integrity check).</p>
            <form method="post" enctype="multipart/form-data">
              <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
              <input type="file" name="db_file" accept=".db" required style="margin-bottom: 15px; display: block;">
              <button type="submit" class="btn danger">Upload & Overwrite</button>
            </form>
            
            <hr>
            <a href="/" style="color: #6c757d; text-decoration: none;">← Back to Application</a>
          </div>
        </body>
        </html>
        """
        return render_template_string(html_template, email=user.get("email"), csrf_token=session['csrf_token'])