from functools import wraps
from flask import Flask, session, redirect, url_for, request, render_template_string
from flask_session import Session
from authlib.integrations.flask_client import OAuth
from dash import html, Input, Output, State, no_update
from db import get_person_id_for_user
from dotenv import load_dotenv
import os

# ---------------------------------------------------------
# Flask + OAuth setup
# ---------------------------------------------------------

load_dotenv()
server = Flask(__name__)
server.secret_key = os.environ.get("SECRET_KEY")
server.config["SESSION_TYPE"] = "filesystem"
server.config["SESSION_PERMANENT"] = False
Session(server)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8050/auth/callback")

oauth = OAuth(server)
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    access_token_url="https://oauth2.googleapis.com/token",
    access_token_params=None,
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    authorize_params=None,
    api_base_url="https://www.googleapis.com/oauth2/v1/",
    userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ---------------------------------------------------------
# Auth routes and helpers
# ---------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

@server.before_request
def simulate_local_login():
    """Automatically log in as a fake user for local development."""
    in_docker = os.getcwd() == "/app"
    debug_env = os.environ.get("DEBUG", None)
    if not in_docker and (debug_env is None or debug_env.lower() in ("1", "true", "yes", "on")):
        if "user" not in session:
            session["user"] = {
                "sub": "localdev",
                "email": "localhost@example.com",
                "name": "Local Developer",
                "picture": None,
            }

@server.before_request
def require_login():
    """Enforce login across the entire application."""
    allowed_endpoints = ['login', 'auth_google', 'auth_callback', 'logout', 'unauthorized', 'static']
    
    if request.endpoint in allowed_endpoints:
        return
        
    if "user" not in session:
        return redirect(url_for('login', next=request.path))

@server.route("/login")
def login():
    if "user" in session:
        next_url = request.args.get("next") or "/"
        return redirect(next_url)
    
    login_html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Login - Collaboratorium</title>
      <style>
        body { font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f4f6f8; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; border-top: 5px solid #f28b20; }
        .login-logo { max-width: 120px; height: auto; margin: 0 auto 15px auto; display: block; }
        h1 { color: #212529; margin-bottom: 10px; font-size: 1.75rem; }
        p { color: #6c757d; margin-bottom: 30px; line-height: 1.5; font-size: 0.95rem; }
        .btn-login { background: #f28b20; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block; transition: background 0.2s; }
        .btn-login:hover { background: #d97b1a; }
      </style>
    </head>
    <body>
      <div class="login-card">
        <img src="https://www.idems.international/wp-content/uploads/2024/10/IDEMS_logo-300x65.png" alt="IDEMS Logo" class="login-logo">
        <h1>Collaboratorium</h1>
        <p>An environment for collaborative innovation. Please sign in with your IDEMS account to access the network.</p>
        <a href="/auth/google" class="btn-login">Login with Google</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(login_html)

@server.route("/auth/google")
def auth_google():
    """Trigger the Google OAuth flow."""
    redirect_uri = OAUTH_REDIRECT_URI
    return oauth.google.authorize_redirect(redirect_uri)


@server.route("/auth/callback")
def auth_callback():
    token = oauth.google.authorize_access_token()
    userinfo = oauth.google.get("userinfo").json()
    if not userinfo.get("email").endswith("@idems.international"):
        return redirect(url_for("unauthorized"))
    session["user"] = {
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    next_url = request.args.get("next") or "/"
    return redirect(next_url)

@server.route("/unauthorized")
def unauthorized():
    unauth_html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Access Denied - Collaboratorium</title>
      <style>
        body { font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f4f6f8; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; border-top: 5px solid #dc3545; }
        h1 { color: #dc3545; margin-bottom: 10px; }
        p { color: #6c757d; margin-bottom: 30px; line-height: 1.5; }
        .btn-login { background: #6c757d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block; transition: background 0.2s; }
        .btn-login:hover { background: #5a6268; }
      </style>
    </head>
    <body>
      <div class="login-card">
        <h1>Access Denied</h1>
        <p>You must use an @idems.international email address to access this application.</p>
        <a href="/logout" class="btn-login">Try a different account</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(unauth_html)

@server.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


def register_auth_callbacks(app):
    @app.callback(Output("login-area", "children"), Input("table-selector", "value"))
    def show_login_area(_):
        user = session.get("user")
        if user:
            # Renders a clear user profile layout if logged in
            picture = html.Img(src=user["picture"], style={"height": "35px", "borderRadius": "50%", "marginRight": "10px", "verticalAlign": "middle"}) if user.get("picture") else html.Span()
            return html.Div([
                picture,
                html.Span(f"{user['name']}", style={"fontWeight": "600", "marginRight": "15px", "verticalAlign": "middle", "color": "var(--idems-text)"}),
                html.A("Logout", href="/logout", className="btn btn-sm btn-outline-secondary", style={"verticalAlign": "middle"})
            ])
        else:
            # Fallback (though before_request shouldn't allow an unauthenticated user to see Dash)
            return html.Div(html.A("Login with Google", href="/login", className="btn btn-primary"))

    @app.callback(
        Output("current-person-id", "data"),
        Input("intermediary-loaded", "data"),
        State("current-person-id", "data")
    )
    def populate_person_id(_, current_id):
        # Only fetch and set the person ID once per session to avoid resetting defaults on every DB update
        if current_id is not None:
            return no_update
            
        person_id = get_person_id_for_user(session["user"])
        return person_id