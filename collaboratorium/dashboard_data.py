"""
dashboard_data.py
Read-only queries for the Dashboard page.

Deliberately not schema-generic: the dashboard is a fixed projection over
initiatives, activities and their link tables, so the queries are written by
hand rather than driven by config. Nothing here writes to the database.

All entity tables are append-only and versioned by (id, version); "latest"
below always means the highest version of a given id.
"""
import json
from datetime import datetime, timedelta

from db import db_connect

# Rows whose status is 'deleted' are tombstones and never appear on the page.
_LIVE = "status IS NOT 'deleted'"


def _latest(table, alias):
    """SQL fragment restricting `alias` to the newest version of each id."""
    return (
        f"{alias}.version = (SELECT MAX(v.version) FROM {table} v "
        f"WHERE v.id = {alias}.id)"
    )


def _cutoff_iso(window_days):
    return (datetime.now() - timedelta(days=window_days)).isoformat()


def _rows(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------
# "Mine"
# ---------------------------------------------------------
# An initiative is Mine if any of:
#   - I am the responsible person
#   - I am linked to one of its activities
#   - I created it AND nobody is responsible for it (orphan fallback)
_MINE_INITIATIVE_IDS = f"""
SELECT i.id FROM initiatives i
WHERE {_latest('initiatives', 'i')} AND i.{_LIVE}
  AND (
    i.responsible_person = :me
    OR i.id IN (
      SELECT ail.initiative_id FROM activity_initiative_links ail
      JOIN activity_people_links apl ON apl.activity_id = ail.activity_id
      WHERE apl.person_id = :me AND ail.{_LIVE} AND apl.{_LIVE}
    )
    OR (i.created_by = :me AND i.responsible_person IS NULL)
  )
"""

_MY_ACTIVITY_IDS = f"""
SELECT apl.activity_id FROM activity_people_links apl
WHERE apl.person_id = :me AND apl.{_LIVE}
"""


def _initiative_scope_clause(scope):
    """Restrict initiatives to Mine, or everything."""
    if scope == "mine":
        return f"AND i.id IN ({_MINE_INITIATIVE_IDS})"
    return ""


# ---------------------------------------------------------
# Section 1 — Recently updated
# ---------------------------------------------------------
def recently_updated(person_id, window_days, scope="mine", limit=25):
    """
    Initiatives touched inside the window, each with the activity events that
    touched it. An initiative counts as touched if it was itself written, or
    an activity linked to it was written or newly linked.

    Returns [{id, name, responsible_person, responsible_name, activity_count,
              last_touched, events: [...]}] newest first.
    """
    if scope == "mine" and not person_id:
        return []

    cutoff = _cutoff_iso(window_days)
    conn = db_connect()
    cur = conn.cursor()
    try:
        # Candidate initiatives: touched directly, or via a linked activity.
        cur.execute(
            f"""
            WITH touched AS (
              SELECT i.id AS initiative_id, i.timestamp AS ts
              FROM initiatives i
              WHERE {_latest('initiatives', 'i')} AND i.{_LIVE}
                AND i.timestamp >= :cutoff
                {_initiative_scope_clause(scope)}

              UNION

              SELECT ail.initiative_id, a.timestamp AS ts
              FROM activity_initiative_links ail
              JOIN activities a ON a.id = ail.activity_id
              JOIN initiatives i ON i.id = ail.initiative_id
              WHERE ail.{_LIVE} AND a.{_LIVE}
                AND {_latest('initiatives', 'i')} AND i.{_LIVE}
                AND a.timestamp >= :cutoff
                {_initiative_scope_clause(scope)}

              UNION

              SELECT ail.initiative_id, ail.timestamp AS ts
              FROM activity_initiative_links ail
              JOIN initiatives i ON i.id = ail.initiative_id
              WHERE ail.{_LIVE}
                AND {_latest('initiatives', 'i')} AND i.{_LIVE}
                AND ail.timestamp >= :cutoff
                {_initiative_scope_clause(scope)}
            )
            SELECT i.id,
                   i.name,
                   i.responsible_person,
                   i.created_by,
                   p.name AS responsible_name,
                   MAX(t.ts) AS last_touched,
                   (SELECT COUNT(DISTINCT l.activity_id)
                      FROM activity_initiative_links l
                     WHERE l.initiative_id = i.id AND l.{_LIVE}) AS activity_count
            FROM touched t
            JOIN initiatives i ON i.id = t.initiative_id
            LEFT JOIN people p
              ON p.id = i.responsible_person AND {_latest('people', 'p')}
            WHERE {_latest('initiatives', 'i')} AND i.{_LIVE}
            GROUP BY i.id
            -- Initiatives with nothing linked belong to the new/quiet boxes;
            -- excluding them here keeps every row on the page unique.
            HAVING activity_count > 0
            ORDER BY last_touched DESC
            LIMIT :limit
            """,
            {"me": person_id, "cutoff": cutoff, "limit": limit},
        )
        initiatives = _rows(cur)
        if not initiatives:
            return []

        # Activity events per initiative, inside the window. person_on marks the
        # activities the viewer is personally linked to: on an initiative they own
        # they see the whole stream, but on one they're only involved in (via an
        # activity) they should see only their own work, not the owner's — one
        # incidental link shouldn't flood the feed with someone else's activity.
        ids = [i["id"] for i in initiatives]
        marks = ",".join("?" * len(ids))
        # One row per activity, not per version: MAX(a.version) with a bare
        # column list is SQLite's documented "row holding the maximum" form, so
        # an activity written three times in the window reads as its latest
        # touch rather than three near-identical lines.
        cur.execute(
            f"""
            SELECT ail.initiative_id,
                   a.id   AS activity_id,
                   a.name AS activity_name,
                   MAX(a.version) AS version,
                   a.timestamp,
                   a.created_by,
                   p.name AS actor_name,
                   EXISTS(SELECT 1 FROM activity_people_links apl
                          WHERE apl.activity_id = a.id AND apl.person_id = ?
                            AND apl.{_LIVE}) AS person_on
            FROM activity_initiative_links ail
            JOIN activities a ON a.id = ail.activity_id
            LEFT JOIN people p
              ON p.id = a.created_by AND p.version = (
                   SELECT MAX(v.version) FROM people v WHERE v.id = p.id)
            WHERE ail.initiative_id IN ({marks})
              AND ail.status IS NOT 'deleted'
              AND a.status IS NOT 'deleted'
              AND a.timestamp >= ?
            GROUP BY ail.initiative_id, a.id
            ORDER BY a.timestamp DESC
            """,
            [person_id] + ids + [cutoff],
        )
        events = _rows(cur)

        by_initiative = {}
        for e in events:
            e["verb"] = "added" if e["version"] == 1 else "edited"
            by_initiative.setdefault(e["initiative_id"], []).append(e)

        result = []
        for i in initiatives:
            owned = i["responsible_person"] == person_id or (
                i["responsible_person"] is None and i["created_by"] == person_id
            )
            evs = by_initiative.get(i["id"], [])
            if scope == "mine" and not owned:
                # Only involved via an activity: show just my own activities, and
                # drop the initiative entirely if none of them are mine in-window.
                evs = [e for e in evs if e["person_on"]]
                if not evs:
                    continue
                i["activity_count"] = len(evs)
                i["involved_only"] = True
            else:
                i["involved_only"] = False
            i["events"] = evs[:5]
            result.append(i)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------
# Section 2 — Near your work (Mine only)
# ---------------------------------------------------------
def near_your_work(person_id, window_days, limit=10):
    """
    Activities somebody else recorded against an initiative that is yours —
    whether you own it or are involved in it via one of your own activities —
    where you are not yet linked to the activity. The prompt is "you may have
    been part of this", hence the exclusion of activities you're already on.

    Each row carries `owned` = you're the responsible person for its initiative.
    The default view shows only owned rows; the involved-in rows (owned == 0) are
    the broadened set, revealed on demand, so one incidental activity link doesn't
    flood the section with a busy initiative's whole history.

    Scoped to Mine-initiatives (reusing _MINE_INITIATIVE_IDS). `limit` applies to
    each group (owned / involved) separately.
    """
    if not person_id:
        return []

    cutoff = _cutoff_iso(window_days)
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT a.id        AS activity_id,
                   a.name      AS activity_name,
                   a.timestamp,
                   i.id        AS initiative_id,
                   i.name      AS initiative_name,
                   p.name      AS actor_name,
                   a.created_by,
                   (i.responsible_person = :me) AS owned
            FROM activity_initiative_links ail
            JOIN activities a ON a.id = ail.activity_id
            JOIN initiatives i ON i.id = ail.initiative_id
            LEFT JOIN people p
              ON p.id = a.created_by AND {_latest('people', 'p')}
            WHERE ail.{_LIVE} AND a.{_LIVE}
              AND {_latest('activities', 'a')}
              AND {_latest('initiatives', 'i')} AND i.{_LIVE}
              AND i.id IN ({_MINE_INITIATIVE_IDS})
              AND a.timestamp >= :cutoff
              AND (a.created_by IS NULL OR a.created_by != :me)
              AND a.id NOT IN ({_MY_ACTIVITY_IDS})
            GROUP BY a.id, i.id
            ORDER BY a.timestamp DESC
            """,
            {"me": person_id, "cutoff": cutoff},
        )
        rows = _rows(cur)
        owned = [r for r in rows if r["owned"]][:limit]
        involved = [r for r in rows if not r["owned"]][:limit]
        return owned + involved
    finally:
        conn.close()


# ---------------------------------------------------------
# Sections 3 & 4 — initiatives with no activity linked
# ---------------------------------------------------------
def _empty_initiatives(person_id, window_days, scope, created_inside_window, limit):
    """
    Initiatives with nothing linked. Split on the window so the two boxes never
    show the same row: `new` was created inside it, `quiet` before it.
    """
    if scope == "mine" and not person_id:
        return []

    cutoff = _cutoff_iso(window_days)
    comparison = ">=" if created_inside_window else "<"
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT i.id,
                   i.name,
                   i.responsible_person,
                   i.created_by,
                   p.name AS responsible_name,
                   c.name AS creator_name,
                   (SELECT MIN(v.timestamp) FROM initiatives v WHERE v.id = i.id)
                     AS created_at,
                   i.timestamp AS last_touched
            FROM initiatives i
            LEFT JOIN people p
              ON p.id = i.responsible_person AND {_latest('people', 'p')}
            LEFT JOIN people c
              ON c.id = i.created_by AND {_latest('people', 'c')}
            WHERE {_latest('initiatives', 'i')} AND i.{_LIVE}
              {_initiative_scope_clause(scope)}
              AND i.id NOT IN (
                SELECT l.initiative_id FROM activity_initiative_links l
                WHERE l.{_LIVE}
              )
              AND (SELECT MIN(v.timestamp) FROM initiatives v WHERE v.id = i.id)
                  {comparison} :cutoff
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"me": person_id, "cutoff": cutoff, "limit": limit},
        )
        return _rows(cur)
    finally:
        conn.close()


def new_without_activity(person_id, window_days, scope="mine", limit=10):
    """Created inside the window, nothing linked yet."""
    return _empty_initiatives(person_id, window_days, scope, True, limit)


def quiet_initiatives(person_id, window_days, limit=10):
    """
    Created before the window and still nothing linked. Mine only, always:
    scoped to yourself this is a personal to-do; scoped to everyone it would
    be a report on other people's neglected projects.
    """
    return _empty_initiatives(person_id, window_days, "mine", False, limit)


# ---------------------------------------------------------
# Section 5 — activities not linked to any initiative (Mine only)
# ---------------------------------------------------------
def unlinked_activities(person_id, limit=10):
    """Activities you're on that hang off no initiative, so no report reaches them."""
    if not person_id:
        return []

    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT a.id, a.name, a.timestamp
            FROM activities a
            WHERE {_latest('activities', 'a')} AND a.{_LIVE}
              AND a.id IN ({_MY_ACTIVITY_IDS})
              AND a.id NOT IN (
                SELECT l.activity_id FROM activity_initiative_links l
                WHERE l.{_LIVE}
              )
            ORDER BY a.timestamp DESC
            LIMIT :limit
            """,
            {"me": person_id, "limit": limit},
        )
        return _rows(cur)
    finally:
        conn.close()


# ---------------------------------------------------------
# Tag groups
# ---------------------------------------------------------
def tag_group_definitions():
    """
    {group_id: key_values} for the newest version of each tag group, used to
    turn a stored tag value into the label a person chose from.
    """
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT t.id, t.key_values FROM tag_groups t
            WHERE {_latest('tag_groups', 't')} AND t.{_LIVE}
            """
        )
        defs = {}
        for gid, key_values in cur.fetchall():
            try:
                defs[str(gid)] = json.loads(key_values) if key_values else {}
            except (json.JSONDecodeError, TypeError):
                defs[str(gid)] = {}
        return defs
    finally:
        conn.close()


def format_tags(raw, defs):
    """
    Turn a stored tag_groups value into [(label, text)].

    Two shapes exist in the data: the structured
    {"<group_id>": {"<element>": ["<option>"]}}, and bare strings left by the
    original import. Both have to render, and neither should ever surface as
    raw JSON on the card.
    """
    if raw in (None, ""):
        return []

    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return [(None, str(raw))]

    if not isinstance(value, dict):
        return [(None, str(value))]

    out = []
    for group_id, elements in value.items():
        if not isinstance(elements, dict):
            out.append((None, str(elements)))
            continue
        key_values = defs.get(str(group_id), {})
        for element_key, element_val in elements.items():
            cfg = key_values.get(element_key, {})
            label = cfg.get("label") or element_key.replace("_", " ").title()
            list_name = cfg.get("list_name")
            options = cfg.get(list_name, {}) if list_name else {}
            vals = element_val if isinstance(element_val, list) else [element_val]
            text = ", ".join(
                str(options.get(v, str(v).replace("_", " ").title()))
                for v in vals
                if v not in (None, "")
            )
            if text:
                out.append((label, text))
    return out


# ---------------------------------------------------------
# Detail cards
# ---------------------------------------------------------
def _one(cur):
    row = cur.fetchone()
    if not row:
        return None
    return dict(zip([c[0] for c in cur.description], row))


def _person_name(cur, person_id):
    if not person_id:
        return None
    cur.execute(
        f"SELECT name FROM people p WHERE p.id = ? AND {_latest('people', 'p')}",
        (person_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def initiative_name(initiative_id):
    """The current name of one initiative, for labelling. None if it's gone."""
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT name FROM initiatives i "
            f"WHERE i.id = ? AND {_latest('initiatives', 'i')} AND i.{_LIVE}",
            (initiative_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def person_name(person_id):
    """The current name of one person, for labelling. None if unknown."""
    if not person_id:
        return None
    conn = db_connect()
    cur = conn.cursor()
    try:
        return _person_name(cur, person_id)
    finally:
        conn.close()


def initiative_detail(initiative_id):
    """Everything the card shows for one initiative, including what it links to."""
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT i.id, i.name, i.description, i.status, i.tag_groups,
                   i.responsible_person, i.created_by, i.version,
                   i.timestamp AS last_updated,
                   (SELECT MIN(v.timestamp) FROM initiatives v WHERE v.id = i.id)
                     AS created_at
            FROM initiatives i
            WHERE i.id = :id AND {_latest('initiatives', 'i')}
            """,
            {"id": initiative_id},
        )
        detail = _one(cur)
        if not detail:
            return None
        detail["responsible_name"] = _person_name(cur, detail["responsible_person"])
        detail["creator_name"] = _person_name(cur, detail["created_by"])

        # Activities linked to it
        cur.execute(
            f"""
            SELECT a.id, a.name, a.start_date, a.end_date, a.timestamp
            FROM activity_initiative_links l
            JOIN activities a ON a.id = l.activity_id
            WHERE l.initiative_id = :id AND l.{_LIVE}
              AND {_latest('activities', 'a')} AND a.{_LIVE}
            ORDER BY a.timestamp DESC
            """,
            {"id": initiative_id},
        )
        detail["activities"] = _rows(cur)

        # Parents and children, which the initiative tree already encodes
        cur.execute(
            f"""
            SELECT i.id, i.name, 'parent' AS relation
            FROM initiative_initiative_links l
            JOIN initiatives i ON i.id = l.parent_id
            WHERE l.child_id = :id AND l.{_LIVE}
              AND {_latest('initiatives', 'i')} AND i.{_LIVE}
            UNION
            SELECT i.id, i.name, 'child' AS relation
            FROM initiative_initiative_links l
            JOIN initiatives i ON i.id = l.child_id
            WHERE l.parent_id = :id AND l.{_LIVE}
              AND {_latest('initiatives', 'i')} AND i.{_LIVE}
            ORDER BY relation, i.name
            """,
            {"id": initiative_id},
        )
        detail["related"] = _rows(cur)

        # People reachable through its activities
        cur.execute(
            f"""
            SELECT DISTINCT p.id, p.name
            FROM activity_initiative_links l
            JOIN activity_people_links pl ON pl.activity_id = l.activity_id
            JOIN people p ON p.id = pl.person_id
            WHERE l.initiative_id = :id AND l.{_LIVE} AND pl.{_LIVE}
              AND {_latest('people', 'p')}
            ORDER BY p.name
            """,
            {"id": initiative_id},
        )
        detail["people"] = _rows(cur)
        return detail
    finally:
        conn.close()


def activity_detail(activity_id):
    """Everything the card shows for one activity."""
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT a.id, a.name, a.description, a.status, a.tag_groups,
                   a.location, a.start_date, a.end_date, a.created_by, a.version,
                   a.timestamp AS last_updated,
                   (SELECT MIN(v.timestamp) FROM activities v WHERE v.id = a.id)
                     AS created_at
            FROM activities a
            WHERE a.id = :id AND {_latest('activities', 'a')}
            """,
            {"id": activity_id},
        )
        detail = _one(cur)
        if not detail:
            return None
        detail["creator_name"] = _person_name(cur, detail["created_by"])

        cur.execute(
            f"""
            SELECT i.id, i.name
            FROM activity_initiative_links l
            JOIN initiatives i ON i.id = l.initiative_id
            WHERE l.activity_id = :id AND l.{_LIVE}
              AND {_latest('initiatives', 'i')} AND i.{_LIVE}
            ORDER BY i.name
            """,
            {"id": activity_id},
        )
        detail["initiatives"] = _rows(cur)

        cur.execute(
            f"""
            SELECT p.id, p.name, l.type
            FROM activity_people_links l
            JOIN people p ON p.id = l.person_id
            WHERE l.activity_id = :id AND l.{_LIVE}
              AND {_latest('people', 'p')}
            ORDER BY p.name
            """,
            {"id": activity_id},
        )
        detail["people"] = _rows(cur)
        return detail
    finally:
        conn.close()


def my_totals(person_id):
    """Counts for the header line. Never per-person totals for anyone else."""
    if not person_id:
        return {"initiatives": 0, "activities": 0}

    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM ({_MINE_INITIATIVE_IDS})", {"me": person_id}
        )
        initiatives = cur.fetchone()[0]
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT a.id) FROM activities a
            WHERE {_latest('activities', 'a')} AND a.{_LIVE}
              AND a.id IN ({_MY_ACTIVITY_IDS})
            """,
            {"me": person_id},
        )
        activities = cur.fetchone()[0]
        return {"initiatives": initiatives, "activities": activities}
    finally:
        conn.close()
