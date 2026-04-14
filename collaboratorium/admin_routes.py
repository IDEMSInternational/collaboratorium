import os
from flask import send_file, request, abort, render_template_string, session
from auth import login_required

# Load authorized admin emails from the environment
ADMIN_EMAILS = [email.strip() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()]

def register_admin_routes(server):
    """Registers the /admin/maintenance route onto the main Flask server."""
    
    @server.route('/admin/maintenance', methods=['GET', 'POST'])
    @login_required
    def admin_maintenance():
        user = session.get("user")
        
        # 1. Security Check: Restrict access to designated admins
        if not user or user.get("email") not in ADMIN_EMAILS:
            abort(403, description="Unauthorized: You do not have admin privileges.")

        db_path = os.path.abspath("database.db")

        # 2. Handle Database Restore (Upload)
        if request.method == 'POST':
            if 'db_file' not in request.files:
                return "No file uploaded.", 400
                
            file = request.files['db_file']
            if file.filename == '':
                return "No file selected.", 400
                
            if file and file.filename.endswith('.db'):
                # Save the uploaded file, overwriting the current database
                file.save(db_path)
                return """
                    <div style="font-family: sans-serif; margin: 40px;">
                        <h2 style="color: green;">✅ Database restored successfully!</h2>
                        <p>Because SQLite connections are created per-request, the changes are live immediately.</p>
                        <a href="/">Return to Dashboard</a>
                    </div>
                """
            return "Invalid file type. Please upload a .db file.", 400

        # 3. Handle Database Backup (Download)
        if request.args.get('action') == 'download':
            if not os.path.exists(db_path):
                abort(404, description="Database file not found.")
            return send_file(db_path, as_attachment=True, download_name="collaboratorium_backup.db")

        # 4. Serve the Admin UI
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
            <p>Download a snapshot of the current SQLite database.</p>
            <a href="/admin/maintenance?action=download" class="btn">Download database.db</a>
            
            <hr>
            
            <h3>2. Restore Database</h3>
            <p style="color: #dc3545;"><strong>Warning:</strong> This will instantly overwrite the live database.</p>
            <form method="post" enctype="multipart/form-data">
              <input type="file" name="db_file" accept=".db" required style="margin-bottom: 15px; display: block;">
              <button type="submit" class="btn danger">Upload & Overwrite</button>
            </form>
            
            <hr>
            <a href="/" style="color: #6c757d; text-decoration: none;">← Back to Application</a>
          </div>
        </body>
        </html>
        """
        return render_template_string(html_template, email=user.get("email"))