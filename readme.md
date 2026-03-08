# BYU-Idaho Class Schedule Foot-Traffic Analysis

This project extracts BYU-Idaho course schedule data from an HTML export, normalizes it into SQLite tables, and analyzes when and where campus is most and least busy.

The analysis focuses on:
- Total registered students by building
- Peak campus concurrency (including overlapping class times)
- Minimum non-zero campus concurrency
- Heatmap visualizations for total, max-time, and min-time traffic

## Instructions for Build and Use

Steps to build and/or run the software:

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Import raw HTML course data into `courses.db`:
   - `python extract_courses.py`
4. Normalize schedule fields and generate analytics tables in `parsed.db`:
   - `python normalize_schedule.py`
5. Render the report:
   - `quarto render analysis.qmd`
6. Open `analysis.html` in a browser.

Instructions for using the software:

1. Ensure the source HTML file exists in the project root:
   - `Course Search - Search Results BYUI _ Public Course Search _ Class Schedule _ BYU-Idaho's Personalized Access.html`
2. Run the pipeline in order:
   - `extract_courses.py` -> `normalize_schedule.py` -> `analysis.qmd`
3. Review generated outputs:
   - `courses.db` (raw extracted table)
   - `parsed.db` (`courses` normalized + `meetings` exploded table)
   - `analysis.html` (final visual report)

## Development Environment

To recreate the development environment, you need the following software and/or libraries:

- Python 3.13 (project has been run with Python 3.13)
- SQLite (via Python standard library `sqlite3`)
- Quarto CLI
- `beautifulsoup4`
- `pandas`
- `folium`
- `ipykernel`
- `lets-plot`
- `quarto` (Python package used in environment)

Install Python packages with:

- `pip install -r requirements.txt`

## Useful Websites to Learn More

I found these websites useful in developing this software:

- https://bytescout.com/blog/plotting-geographical-heatmaps-using-python-folium-library.html

- https://pandas.pydata.org/Pandas_Cheat_Sheet.pdf

## Future Work

The following items I plan to fix, improve, and/or add to this project in the future:

- [ ] Add trend charts (bar/line) in addition to folium heatmaps.
- [ ] Add automated validation tests for parser outputs and time-overlap logic.
- [ ] Allow time selection so you can see how traffic changes throughout the day.