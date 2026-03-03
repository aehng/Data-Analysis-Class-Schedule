import re
import pandas as pd
import sqlite3


# earlier version used a strict regex that failed for some
# strings (multi-word buildings, "Arranged", missing day codes, etc.).
# we'll replace it with a more forgiving parser below.


# schedule regex is now only used for a simple match; parsing is manual
_schedule_re = re.compile(r"\(([^)]+)\)")  # capture dates inside ()


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


def add_normalized_columns(df: pd.DataFrame, col: str = "schedule") -> pd.DataFrame:
    """Return a new DataFrame with parsed schedule columns added.

    The original column is left in place; new columns are named
    ``<col>_days``, ``<col>_time``, etc.
    """
    parsed = df[col].apply(parse_schedule).apply(pd.Series)
    parsed.columns = [f"{col}_{c}" for c in parsed.columns]
    return pd.concat([df, parsed], axis=1)


if __name__ == "__main__":
    # quick demonstration + full run when executed as a script
    conn = sqlite3.connect("courses.db")
    # grab every column so we can reproduce the full table later
    df = pd.read_sql_query("SELECT * FROM courses", conn)
    conn.close()

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
    BUILDINGS = [
        "ASC", "Ag Engineering Bldg", "Austin", "BEN", "Benson",
        "Clarke", "Court", "ETC", "Hart", "Hinckley", "MC", "Ricks",
        "Romney", "STC", "Smith", "Snow", "Spori", "Taylor",
        "Taylor Chapel", "University Comm Bldg",
    ]

    # optionally log the candidate values for debugging
    df['building_candidate'] = df['schedule'].apply(candidate_building)
    candidates = sorted({b for b in df['building_candidate'].dropna().unique()})
    print("\ncandidate buildings (seen in raw data):\n", candidates)

    # force every schedule_building to one of the BUILDINGS list, if possible.
    def fill_building(row):
        bld = row['schedule_building']
        if pd.isna(bld) or not bld:
            for b in BUILDINGS:
                if b and b in row['schedule']:
                    return b
        return bld

    df2['schedule_building'] = df2.apply(fill_building, axis=1)

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

    # write the extended dataframe into a new sqlite database
    out_conn = sqlite3.connect("parsed.db")
    # overwrite if it already exists
    df2.to_sql("courses", out_conn, if_exists="replace", index=False)
    out_conn.close()
    print("\nWrote normalized table to parsed.db")
