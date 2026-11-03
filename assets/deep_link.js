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
    // Only an edit route is worth restoring, and the stash is whatever was in
    // the address bar of whoever sent the visitor to the login page. It is put
    // back by assigning location.hash, so the worst it could do is name a
    // record the visitor did not ask for — but a stash that outlived its login
    // (abandoned sign-in, then a plain visit later in the same tab) would do
    // that to an unrelated visit, so anything but a route is dropped.
    var ROUTE = /^#edit\/[A-Za-z0-9_]+\/\d+$/;
    try {
        var pending = sessionStorage.getItem(KEY);
        if (!pending) {
            return;
        }
        sessionStorage.removeItem(KEY);
        if (!ROUTE.test(pending)) {
            return;
        }
        // A fragment already in the URL is the one the visitor asked for now.
        if (!window.location.hash) {
            window.location.hash = pending;
        }
    } catch (e) {
        // Storage can be refused outright (private browsing, blocked cookies).
        // A deep link that fails to survive login is not worth a broken page.
    }
})();
