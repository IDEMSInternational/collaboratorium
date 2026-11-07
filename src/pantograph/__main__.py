"""
Run the app: ``python -m pantograph``.

Paths come from the environment (PANTOGRAPH_CONFIG, PANTOGRAPH_DB,
PANTOGRAPH_ANALYTICS_DB, PANTOGRAPH_ASSETS) via pantograph.settings.

With no arguments this serves, which is what the Dockerfile's ENTRYPOINT
depends on. Subcommands are for things done *to* a deployment rather than with
it — exporting the producer contract, for now.
"""
import argparse
import os
import sys

from pantograph.settings import configure


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="pantograph",
        description="A config-driven database viewer and form engine.",
    )
    parser.add_argument(
        "--config", default=None,
        help="Config file or directory (default: PANTOGRAPH_CONFIG, else ./config)",
    )
    # `required=False` so that the bare invocation keeps serving: the container
    # entrypoint is `python -m pantograph` with no arguments, and that must not
    # become an argparse error.
    sub = parser.add_subparsers(dest="command")

    export = sub.add_parser(
        "export-contract",
        help="Write the producer contract, derived from the config, as JSON.",
        description=(
            "Emit what an external tool needs in order to propose records: "
            "tables, elements, types, choice sources and required/relevant "
            "conditions, with a hash of the config it came from."
        ),
    )
    export.add_argument(
        "--out", default="-",
        help="Where to write it; '-' (the default) writes to stdout.",
    )
    return parser


def _export_contract(args):
    from pantograph import contract
    from pantograph.config import ConfigError, load_config
    from pantograph.settings import get_settings

    try:
        config = load_config(get_settings().config_path)
    except ConfigError as exc:
        # The message already says what to do about it; a traceback on top of
        # it just buries the one line worth reading. The server path can keep
        # raising, where a stack trace goes to a log rather than to a person.
        print(f"pantograph: {exc}", file=sys.stderr)
        return 2

    document = contract.dumps(config)
    if args.out == "-":
        sys.stdout.write(document)
    else:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(document)
        # To stderr, so `--out -` piped into a validator stays clean while a
        # person running it with a path still gets told what happened.
        print(f"Wrote {args.out}", file=sys.stderr)
    return 0


def _serve():
    from pantograph.app import create_app

    in_docker = os.getcwd() == "/app"
    default_host = "0.0.0.0" if in_docker else "127.0.0.1"

    host = os.environ.get("HOST", default_host)
    port = int(os.environ.get("PORT", "8050"))
    debug_env = os.environ.get("DEBUG", None)
    debug = not in_docker if debug_env is None else debug_env.lower() in ("1", "true", "yes", "on")

    app = create_app()
    print(f"Starting server on {host}:{port} (in_docker={in_docker}, debug={debug})")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
    return 0


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.config:
        configure(config_path=args.config)

    if args.command == "export-contract":
        return _export_contract(args)
    return _serve()


if __name__ == "__main__":
    sys.exit(main())
