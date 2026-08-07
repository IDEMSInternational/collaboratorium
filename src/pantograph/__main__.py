"""
Run the app: ``python -m pantograph``.

Paths come from the environment (PANTOGRAPH_CONFIG, PANTOGRAPH_DB,
PANTOGRAPH_ANALYTICS_DB, PANTOGRAPH_ASSETS) via pantograph.settings.
"""
import os

from pantograph.app import create_app


def main():
    in_docker = os.getcwd() == "/app"
    default_host = "0.0.0.0" if in_docker else "127.0.0.1"

    host = os.environ.get("HOST", default_host)
    port = int(os.environ.get("PORT", "8050"))
    debug_env = os.environ.get("DEBUG", None)
    debug = not in_docker if debug_env is None else debug_env.lower() in ("1", "true", "yes", "on")

    app = create_app()
    print(f"Starting server on {host}:{port} (in_docker={in_docker}, debug={debug})")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
