import sqlite3
import os
from bs4 import BeautifulSoup

html_path = os.path.join(os.path.dirname(__file__),
                         "Course Search - Search Results BYUI _ Public Course Search _ Class Schedule _ BYU-Idaho's Personalized Access.html")

def parse_html(html_file):
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    table = soup.find('table', id='tableCourses')
    if not table:
        raise RuntimeError('Could not find courses table in HTML')

    headers = []
    for th in table.find_all('th'):
        text = th.get_text(strip=True)
        headers.append(text)

    # The first few headers are grouped, so we'll use the known column names
    columns = ['Add', 'Course-Section', 'Title', 'Credits', 'Schedule', 'Class Type', 'Delivery Method']

    data = []
    for tr in table.find('tbody').find_all('tr'):
        cells = [td.get_text(strip=True) for td in tr.find_all('td')]
        if len(cells) != len(columns):
            # skip rows that aren't data rows
            continue
        data.append(cells)
    return columns, data


def ensure_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS courses (
        add_button TEXT,
        course_section TEXT,
        title TEXT,
        credits TEXT,
        schedule TEXT,
        class_type TEXT,
        delivery_method TEXT
    )
    ''')
    conn.commit()
    return conn


def main():
    columns, rows = parse_html(html_path)
    db_file = os.path.join(os.path.dirname(__file__), 'courses.db')
    conn = ensure_db(db_file)
    c = conn.cursor()

    c.execute('DELETE FROM courses')
    for row in rows:
        c.execute('INSERT INTO courses VALUES (?, ?, ?, ?, ?, ?, ?)', row)
    conn.commit()
    conn.close()
    print(f"Imported {len(rows)} rows into {db_file}")


if __name__ == '__main__':
    main()
