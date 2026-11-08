"""
Make a failed callback visible, and findable.

A Dash callback that raises does not break the page. The browser gets a 500, the
component the callback was meant to fill stays as it was, and nothing on screen
says anything happened: a review queue that should have held seven records was an
empty heading, and the only trace was a traceback in a server log nobody was
reading. That is the worst way for this to fail, because it looks exactly like
"there is nothing here".

This does the server half. Every unhandled exception while serving a callback is
logged once, with a short reference and the callback's outputs, and the 500
carries that reference in an `X-Error-Id` header. `assets/callback_failures.js`
does the browser half: it shows a banner quoting the reference, so whoever saw
the problem can hand over something that finds it in the log in one search.

It listens for the exception rather than handling it, so it changes nothing about
what the response is or how an error elsewhere in the app is reported.
"""
import logging
import uuid

from flask import got_request_exception, request

log = logging.getLogger("pantograph.callbacks")

_DASH_UPDATE = "/_dash-update-component"
HEADER = "X-Error-Id"
_KEY = "pantograph.callback_error_id"


def _outputs(payload):
    """The callback's output ids, as Dash sends them, for the log line."""
    if not isinstance(payload, dict):
        return None
    return payload.get("output")


def install(server):
    """Wire the logging and the header onto the Flask server. Safe to call twice."""
    if server.extensions.get("pantograph_failures"):
        return
    server.extensions["pantograph_failures"] = True

    def _record(sender, exception, **extra):
        if not request.path.startswith(_DASH_UPDATE):
            return
        # On the request, not `g`: `g` lives as long as the app context, which a
        # test server or a long-lived context keeps across requests, and an id
        # left there would be stamped onto an unrelated later failure.
        error_id = request.environ[_KEY] = uuid.uuid4().hex[:8]
        log.error(
            "Callback failed [%s] output=%s",
            error_id, _outputs(request.get_json(silent=True)),
            exc_info=exception)

    # Not weak: the receiver is a local function, and a signal holds receivers
    # by weak reference, so it would be collected before the first request.
    got_request_exception.connect(_record, server, weak=False)

    @server.after_request
    def _tag(response):
        error_id = request.environ.get(_KEY)
        if error_id and response.status_code >= 500:
            response.headers[HEADER] = error_id
            # The browser only lets a script read a response header it is told
            # is safe to read.
            response.headers["Access-Control-Expose-Headers"] = HEADER
        return response
