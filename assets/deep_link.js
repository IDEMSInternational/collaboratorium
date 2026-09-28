/*
 * Carry an "#edit/..." deep link across the login round trip.
 *
 * A URL fragment is never sent to the server, so `next=` cannot hold it and
 * the trip out to Google and back to "/" drops it: a logged-out visitor
 * following a link out of a report would arrive at the dashboard with nothing
 * open. The login page stashes the fragment on the way out (see auth.py) and
 * this puts it back on the way in, before dcc.Location reads the URL.
 */
(function () {
    var KEY = "pantograph-pending-hash";
    try {
        var pending = sessionStorage.getItem(KEY);
        if (!pending) {
            return;
        }
        sessionStorage.removeItem(KEY);
        // A fragment already in the URL is the one the visitor asked for now.
        if (!window.location.hash) {
            window.location.hash = pending;
        }
    } catch (e) {
        // Storage can be refused outright (private browsing, blocked cookies).
        // A deep link that fails to survive login is not worth a broken page.
    }
})();
