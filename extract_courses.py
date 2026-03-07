import sqlite3
import os
from bs4 import BeautifulSoup

html_path = os.path.join(os.path.dirname(__file__),
                         "Course Search - Search Results BYUI _ Public Course Search _ Class Schedule _ BYU-Idaho's Personalized Access.html")

def sanitize_header(name: str) -> str:
    """Turn a header string into a safe sqlite column name.

    - Drop any parenthetical remarks.
    - Replace spaces and dashes with underscores.
    - Remove any remaining non‑word characters and lowercase.
    """
    import re
    name = name.strip()
    name = re.sub(r"\s*\(.*\)", "", name)           # remove ( ... )
    name = name.replace('-', '_').replace(' ', '_')        # normalize separators
    name = re.sub(r"[^\w]", "", name)                  # drop anything else
    return name.lower()


def parse_html(html_file):
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    table = soup.find('table', id='tableCourses')
    if not table:
        raise RuntimeError('Could not find courses table in HTML')

    # collect the text of each <th>; the first one is just a grouping header
    raw_headers = [th.get_text(strip=True) for th in table.find_all('th')]
    # drop any empty or purely grouping headers
    headers = [h for h in raw_headers if h and h.lower() != 'courses']

    # convert to sanitized sqlite column names for the database
    columns = [sanitize_header(h) for h in headers]

    data = []
    for tr in table.find('tbody').find_all('tr'):
        cells = [td.get_text(strip=True) for td in tr.find_all('td')]
        if len(cells) != len(columns):
            # skip rows that aren't data rows (maybe footable spacing rows etc.)
            continue
        data.append(cells)
    return columns, data


def ensure_db(db_path, columns):
    """Ensure the database exists with a table called ``courses`` having
    the supplied ``columns`` (all TEXT).

    ``columns`` should already be sanitized.  If the existing table has a
    different set of columns we drop it and recreate so the schema stays in
    sync with the HTML.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # inspect current columns, if any
    c.execute("PRAGMA table_info(courses)")
    existing = [row[1] for row in c.fetchall()]
    if existing and existing != columns:
        # schema changed; wipe table and start over
        c.execute("DROP TABLE courses")
        existing = []

    if not existing:
        # build a ``col TEXT`` list joined by commas
        col_defs = ',\n        '.join(f'"{col}" TEXT' for col in columns)
        c.execute(f'''
        CREATE TABLE courses (
            {col_defs}
        )
        ''')
    conn.commit()
    return conn


def main():
    columns, rows = parse_html(html_path)
    db_file = os.path.join(os.path.dirname(__file__), 'courses.db')
    conn = ensure_db(db_file, columns)
    c = conn.cursor()

    # clear out any old data before inserting; keep schema intact
    c.execute('DELETE FROM courses')
    # build parameter placeholders dynamically
    placeholders = ','.join('?' for _ in columns)
    # quote column identifiers to handle reserved words or spaces
    quoted = [f'"{col}"' for col in columns]
    insert_sql = f'INSERT INTO courses ({",".join(quoted)}) VALUES ({placeholders})'

    for row in rows:
        c.execute(insert_sql, row)
    conn.commit()
    conn.close()
    print(f"Imported {len(rows)} rows into {db_file}")


if __name__ == '__main__':
    main()
