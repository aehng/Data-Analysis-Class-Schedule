import re
import pandas as pd
import sqlite3


# earlier version used a strict regex that failed for some
# strings (multi-word buildings, "Arranged", missing day codes, etc.).
# we'll replace it with a more forgiving parser below.


# schedule regex is now only used for a simple match; parsing is manual
_schedule_re = re.compile(r"\(([^)]+)\)")  # capture dates inside ()


def parse_seats(s: str):
    """Return the integer number of open seats (right of slash) or None.

    The original column contains strings like ``"21 ∕ 30"`` where the
    slash is the unicode division slash (U+2215).  We ignore the total
    and just return the left-hand value as an integer when possible.
    """
    if not isinstance(s, str):
        return None
    # split on any slash-like character
    parts = re.split(r"[\u002F\u2215]", s)
    if len(parts) < 2:
        return None
    try:
        return int(parts[1].strip()) - int(parts[0].strip())
    except ValueError:
        return None


def _normalize_time(t: str):
    """Convert a time like "11:30AM" or "1:45PM" to 24‑hour string.

    Returns ``None`` for invalid input.
    """
    if not t:
        return None
    t = t.strip().upper()
    m = re.match(r"^(\d{1,2}:\d{2})(AM|PM)$", t)
    if not m:
        return None
    hhmm, ampm = m.groups()
    h, mnt = hhmm.split(":")
    h = int(h)
    if ampm == "PM" and h != 12:
        h += 12
    if ampm == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mnt}"


def parse_schedule(s: str) -> dict:
    """Parse a schedule string into components.

    Parameters
    ----------
    s : str
        Raw schedule text from the courses table.

    Returns
    -------
    dict
        A dictionary with keys: days, time_range, time_start,
        time_end, date_range, building, room. If the string doesn't
        match the expected pattern, the original string is returned
        under 'raw' and the other keys are set to ``None``.
    """
    # non-string values just get passed through
    if not isinstance(s, str):
        return {"raw": s, "days": None, "time_range": None,
                "time_start": None, "time_end": None,
                "date_range": None, "building": None, "room": None}

    s = s.strip()
    if not s:
        return {"raw": s, "days": None, "time_range": None,
                "time_start": None, "time_end": None,
                "date_range": None, "building": None, "room": None}

    # extract the date range if present
    date_match = _schedule_re.search(s)
    date_range = date_match.group(1) if date_match else None

    # remove date portion from the string to simplify further parsing
    cleaned = s[:date_match.start()] if date_match else s
    remainder = s[date_match.end():].strip() if date_match else ""
    # if there's a second time segment after the building, drop it so we only
    # parse the first location
    if remainder:
        tpos = re.search(r"\d{1,2}:\d{2}", remainder)
        if tpos:
            remainder = remainder[:tpos.start()].strip()

    # first token(s) may be day codes (letters) followed by time
    days = None
    time_range = None
    time_start = None
    time_end = None
    tokens = cleaned.split()
    if tokens and re.fullmatch(r"[A-Za-z]+", tokens[0]):
        days = tokens[0]
        time_range = " ".join(tokens[1:]) if len(tokens) > 1 else None
    else:
        time_range = cleaned or None

    # if we got a time_range, attempt to split to start/end
    if time_range:
        parts = time_range.split("-")
        if len(parts) == 2:
            a, b = parts[0].strip(), parts[1].strip()
            # if one side lacks AM/PM, inherit from the other side
            if not re.search(r"(AM|PM)$", a, re.IGNORECASE):
                m = re.search(r"(AM|PM)$", b, re.IGNORECASE)
                if m:
                    a += m.group(1)
            if not re.search(r"(AM|PM)$", b, re.IGNORECASE):
                m = re.search(r"(AM|PM)$", a, re.IGNORECASE)
                if m:
                    b += m.group(1)
            time_start = _normalize_time(a)
            time_end = _normalize_time(b)

    # remainder should contain building and possibly room # or descriptive text
    building = None
    room = None
    if remainder:
        parts = remainder.split()
        # special case: the word "Arranged" means no fixed location
        if parts[-1].lower() == "arranged":
            building = "Arranged"
            room = None
        else:
            # find last token containing a digit (room number)
            idx = None
            for i in range(len(parts) - 1, -1, -1):
                tok = parts[i]
                # skip anything that looks like a time range (contains colon)
                if ":" in tok:
                    continue
                if re.search(r"\d", tok):
                    idx = i
                    break
            if idx is not None:
                # building is everything before the number token, with a
                # special case: if the word before the number is a descriptor
                # like "Lab" or "Room", include that word in the room instead.
                prev = parts[idx - 1].lower() if idx > 0 else ""
                descriptors = {"lab", "room", "rm", "studio", "classroom", "hall"}
                if prev in descriptors and idx > 0:
                    building = " ".join(parts[:idx - 1]) if parts[:idx - 1] else None
                    room = " ".join(parts[idx - 1:])
                else:
                    building = " ".join(parts[:idx]) if parts[:idx] else None
                    room = " ".join(parts[idx:])
            else:
                # no numeric tokens; treat first word as building, remainder as
                # room details (e.g. "Snow Classroom Only" -> building="Snow").
                if len(parts) == 1:
                    building = parts[0]
                    room = None
                else:
                    building = parts[0]
                    room = " ".join(parts[1:])

    return {
        "raw": s,
        "days": days,
        "time_range": time_range,
        "time_start": time_start,
        "time_end": time_end,
        "date_range": date_range,
        "building": building,
        "room": room,
    }


def _day_flags(days_str: str) -> dict:
    """Convert a compact day code string (e.g. ``MWF`` or ``TR``)
    into a dict of weekday booleans.

    We map the usual single-letter codes used by the registrar to full
    day names.  If the input is not a string the result is a set of all
    flags ``False``.
    """
    mapping = {
        "M": "mon",
        "T": "tue",
        "W": "wed",
        "R": "thu",
        "F": "fri",
        "S": "sat",  # some courses use S or Su for Saturday/Sunday
        "U": "sun",
    }
    flags = {v: False for v in mapping.values()}
    if isinstance(days_str, str):
        for ch in days_str.upper():
            if ch in mapping:
                flags[mapping[ch]] = True
    return flags


def add_normalized_columns(df: pd.DataFrame, col: str = "schedule") -> pd.DataFrame:
    """Return a new DataFrame with parsed schedule columns added.

    The original column is left in place; new columns are named
    ``<col>_days``, ``<col>_time``, etc.  In addition to the raw
    ``<col>_days`` string produced by :func:`parse_schedule`, we also
    create seven boolean columns (``<col>_mon`` through ``<col>_sun``)
    that indicate whether the course meets on that weekday.  This makes
    it easy to filter the table by individual days without having to
    interpret the compact code.
    """
    parsed = df[col].apply(parse_schedule).apply(pd.Series)
    # expand weekday flags from the unprefixed 'days' column; the
    # renaming happens later, so we don't yet have ``schedule_days``
    weekday_flags = parsed['days'].apply(_day_flags).apply(pd.Series)
    parsed = pd.concat([parsed, weekday_flags], axis=1)

    parsed.columns = [f"{col}_{c}" for c in parsed.columns]
    return pd.concat([df, parsed], axis=1)


def explode_meetings(df: pd.DataFrame, col: str = "schedule") -> pd.DataFrame:
    """Return a DataFrame with one row per weekday/time for each input row.

    The output has columns:

    * ``orig_index`` – original dataframe index so we can trace back if
      needed
    * ``weekday`` – one of ``mon``/``tue``/…/``sun``
    * ``time_start``/``time_end`` – normalized 24‑hour times
    * plus any other fields of interest such as ``building`` or
      ``seats_taken_count``.  The function currently copies the
      building and seat count, but you can extend it.

    This “long” form is convenient for aggregations that involve the
    day-of-week, because each meeting already occupies its own row.

    If the DataFrame already contains normalized schedule columns (e.g.
    ``schedule_mon``, ``schedule_time_start``), those are used directly
    instead of re-parsing, which prevents phantom records from appearing
    due to double-normalization. Rows without valid time_start or building
    are automatically skipped.
    """
    # check if already normalized; if not, normalize it
    if f"{col}_mon" not in df.columns:
        df2 = add_normalized_columns(df, col)
    else:
        df2 = df.copy()
    
    # drop duplicate columns that may exist
    df2 = df2.loc[:, ~df2.columns.duplicated()]

    rows = []
    for idx, r in df2.iterrows():
        for wd in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            flag = r.get(f"{col}_{wd}")
            # flag may be a scalar or a single-element Series; coerce to bool
            if pd.notna(flag) and bool(flag):
                # only add rows where both time_start and building are valid
                ts = r.get(f"{col}_time_start")
                bldg = r.get(f"{col}_building")
                if pd.notna(ts) and pd.notna(bldg):
                    rows.append({
                        "orig_index": idx,
                        "weekday": wd,
                        "time_start": ts,
                        "time_end": r.get(f"{col}_time_end"),
                        "building": bldg,
                        "seats": r.get("seats_taken_count"),
                    })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # quick demonstration + full run when executed as a script
    conn = sqlite3.connect("courses.db")
    # grab every column so we can reproduce the full table later
    df = pd.read_sql_query("SELECT * FROM courses", conn)
    conn.close()

    # compute numeric seats value and keep the original text column
    if 'seats_open' in df.columns:
        df['seats_taken_count'] = df['seats_open'].apply(parse_seats)

    print("original schedules (first 10):\n", df['schedule'].head(10))

    df2 = add_normalized_columns(df)
    print("\nparsed result (first 10 rows):\n", df2.head(10))

    # compute simple building candidates directly from raw schedule text
    def candidate_building(s):
        if not isinstance(s, str):
            return None
        # strip everything through the closing parenthesis of the date range
        # e.g. "...PM(01/07/2026 - 04/09/2026)Smith 383" -> "Smith 383"
        after = re.sub(r"^.*?\)\s*", "", s)
        m = re.match(r"([A-Za-z ]+?)\s*\d", after)
        return m.group(1).strip() if m else None

    # at this point we've parsed schedules, now apply a fixed list
    # of known buildings rather than deriving candidates every time.
    # We also have a small alias table so that multiple names map to
    # a single canonical building.  That handles BEN/Benson and
    # Taylor/Taylor Chapel (and can be extended if new aliases crop up).
    BUILDING_ALIASES = {
        "BEN": "Benson",
        "Benson": "Benson",
        "Taylor Chapel": "Taylor",
        "Taylor": "Taylor",
        # sometimes people abbreviate Austin
        "AUS": "Austin",
        "Court": "Hart",  # some schedules say "Court" but it's actually Hart Building
        "Snow Recital Hall": "Snow",  # some schedules say "Snow Recital Hall" but it's actually Snow Building
        "Barrus Concert Hall": "Snow",  # some schedules say "Barrus Concert Hall" but it's actually Snow Building
        "Snow Drama Theatre": "Snow",
        "Hinckley Cultural Hall AMW": "Hinckley"
    }

    def canonical_name(name):
        if not isinstance(name, str):
            return name
        return BUILDING_ALIASES.get(name, name)

    # canonical buildings list contains the unique set of names we accept
    BUILDINGS = sorted({
        *BUILDING_ALIASES.values(),
        "ASC", "Ag Engineering Bldg", "Austin", "Barrus Concert Hall", "Clarke",
        "ETC", "Hart", "Hinckley", "MC", "McKay", "Ricks",
        "Romney", "STC", "Smith", "Snow", "Spori", "University Comm Bldg",
    })

    # optionally log the candidate values for debugging
    df['building_candidate'] = df['schedule'].apply(candidate_building)
    candidates = sorted({b for b in df['building_candidate'].dropna().unique()})
    print("\ncandidate buildings (seen in raw data):\n", candidates)
    missing = [b for b in candidates if canonical_name(b) not in BUILDINGS]
    if missing:
        print("\n-- buildling names not covered by our canonical list:\n", missing)

    # force every schedule_building to one of the BUILDINGS list, if possible.
    def fill_building(row):
        bld = row['schedule_building']
        if pd.isna(bld) or not bld:
            for b in BUILDINGS:
                if b and b in row['schedule']:
                    return b
        return bld

    df2['schedule_building'] = df2.apply(fill_building, axis=1)

    # map any aliases to canonical names
    df2['schedule_building'] = df2['schedule_building'].apply(canonical_name)

    # blank and eventually drop rows that still are not in BUILDINGS
    df2.loc[~df2.schedule_building.isin(BUILDINGS), 'schedule_building'] = pd.NA
    df2 = df2.dropna(subset=['schedule_building'])

    # recompute room if building was filled from schedule
    def fix_room(row):
        bld = row['schedule_building']
        room = row['schedule_room']
        if isinstance(bld, str) and bld and isinstance(room, str) and room:
            if room.startswith(bld + ' '):
                return room[len(bld)+1:]
        return room

    df2['schedule_room'] = df2.apply(fix_room, axis=1)

    # write the extended dataframe into a new sqlite database; retain
    # both original seats_open text and the newly derived count column.
    out_conn = sqlite3.connect("parsed.db")
    # overwrite if it already exists
    df2.to_sql("courses", out_conn, if_exists="replace", index=False)

    # create the long-form "meetings" table and save it as well
    meetings = explode_meetings(df2)
    meetings.to_sql("meetings", out_conn, if_exists="replace", index=False)

    out_conn.close()
    print("\nWrote normalized table to parsed.db (includes seats_taken_count)")
    print("Also wrote exploded meetings table with one row per weekday/time")
