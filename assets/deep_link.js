/*
 * Carry an editor deep link across the login round trip.
 *
 * A URL fragment is never sent to the server, so `next=` cannot hold it and
 * the trip out to Google and back to "/" drops it: someone following a link
 * out of a report while signed out would arrive at the dashboard with nothing
 * open. The login page stashes the fragment on the way out (see auth.py) and
 * this puts it back on the way in, before dcc.Location reads the URL.
 */
(function () {
    var KEY = "pantograph-pending-hash";
    // The routes pantograph.editor.parse_hash reads, and only those. The stash
    // holds whatever was in the address bar of whoever sent the visitor to the
    // login page, and it is spent by the next load in the tab rather than
    // specifically the one coming back from Google - so an abandoned sign-in
    // would otherwise leave a fragment to open a record on an unrelated visit
    // later. Putting it back only assigns location.hash, so the worst a
    // non-route could do is sit there, but it has no business doing even that.
    var ROUTE = /^#(edit\/[A-Za-z0-9_]+\/\d+|add\/[A-Za-z0-9_]+(\/[A-Za-z0-9_]+\/\d+)?)$/;
    try {
        var pending = sessionStorage.getItem(KEY);
        if (!pending) {
            return;
        }
        sessionStorage.removeItem(KEY);
        if (!ROUTE.test(pending)) {
            return;
        }
        // A fragment already in the URL is the one being asked for now.
        if (!window.location.hash) {
            window.location.hash = pending;
        }
    } catch (e) {
        // Storage can be refused outright (private browsing, blocked cookies).
        // A deep link that fails to survive login is not worth a broken page.
    }
})();
