/*
 * Say so when part of the page fails to update.
 *
 * A Dash callback that raises leaves the component it feeds exactly as it was and
 * shows nothing, so a failure looks like "there is nothing here". This watches
 * the callback requests and, when one fails, puts a banner at the foot of the
 * page with the reference the server logged (see pantograph/failures.py), so
 * the person who saw it can quote something that finds the traceback.
 *
 * It wraps `fetch` and passes everything through untouched; it only looks at
 * the response. It never alters a request or a response, and it is silent for a
 * request the page itself cancelled.
 */
(function () {
    var ENDPOINT = "/_dash-update-component";
    var BANNER_ID = "pantograph-callback-failure";
    var original = window.fetch;
    if (typeof original !== "function") {
        return;
    }

    var failures = [];

    function outputsOf(init) {
        // Which component the failed callback was feeding, for the details line.
        try {
            var body = JSON.parse(init && init.body);
            return String(body.output || "");
        } catch (e) {
            return "";
        }
    }

    function render() {
        var banner = document.getElementById(BANNER_ID);
        if (!banner) {
            banner = document.createElement("div");
            banner.id = BANNER_ID;
            banner.setAttribute("role", "alert");
            banner.style.cssText = [
                "position:fixed", "left:0", "right:0", "bottom:0", "z-index:100000",
                "background:#842029", "color:#fff", "padding:10px 16px",
                "font:14px/1.4 system-ui,sans-serif", "box-shadow:0 -2px 8px rgba(0,0,0,.3)",
                "display:flex", "gap:12px", "align-items:flex-start"
            ].join(";");
            var text = document.createElement("div");
            text.id = BANNER_ID + "-text";
            text.style.flex = "1";
            var close = document.createElement("button");
            close.type = "button";
            close.textContent = "Dismiss";
            close.style.cssText = "background:transparent;color:#fff;border:1px solid #fff;" +
                "border-radius:4px;padding:2px 10px;cursor:pointer";
            close.onclick = function () {
                failures = [];
                banner.remove();
            };
            banner.appendChild(text);
            banner.appendChild(close);
            document.body.appendChild(banner);
        }
        var latest = failures[failures.length - 1];
        var text = document.getElementById(BANNER_ID + "-text");
        text.textContent = "";
        var lead = document.createElement("strong");
        lead.textContent = "Part of this page failed to update. ";
        text.appendChild(lead);
        text.appendChild(document.createTextNode(
            "Something may be missing or out of date. Reload to try again; if it keeps " +
            "happening, tell whoever runs this site" +
            (latest.id ? ", quoting reference " : ".")));
        if (latest.id) {
            var code = document.createElement("code");
            code.textContent = latest.id;
            code.style.cssText = "background:rgba(255,255,255,.2);padding:0 4px;border-radius:3px";
            text.appendChild(code);
            text.appendChild(document.createTextNode("."));
        }
        if (failures.length > 1) {
            text.appendChild(document.createTextNode(" (" + failures.length + " failures so far)"));
        }
        if (latest.output) {
            var detail = document.createElement("div");
            detail.style.cssText = "opacity:.8;font-size:12px;margin-top:2px";
            detail.textContent = "Updating: " + latest.output.slice(0, 160);
            text.appendChild(detail);
        }
    }

    function note(failure) {
        failures.push(failure);
        if (document.body) {
            render();
        } else {
            document.addEventListener("DOMContentLoaded", render);
        }
    }

    window.fetch = function (input, init) {
        var url = typeof input === "string" ? input : (input && input.url) || "";
        if (url.indexOf(ENDPOINT) === -1) {
            return original.apply(this, arguments);
        }
        return original.apply(this, arguments).then(function (response) {
            if (!response.ok) {
                note({
                    id: response.headers.get("X-Error-Id") || "",
                    output: outputsOf(init)
                });
            }
            return response;
        }, function (error) {
            // A request the page cancelled itself (a newer one superseded it) is
            // not a failure. A dropped connection is.
            if (!error || error.name !== "AbortError") {
                note({id: "", output: outputsOf(init)});
            }
            throw error;
        });
    };
})();
