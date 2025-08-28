#!/usr/bin/env python3
# schedule.py
# Generates a monthly schedule calendar and per-person summary from availability responses.
# Also emits per-person .ics feeds and links them in the Excel.
# Usage:
#   python schedule.py \
#     --input availability.xlsx \
#     --month 5 --year 2025 \
#     --output schedule_may_2025.xlsx \
#     --cal-url-base https://raw.githubusercontent.com/you/yourrepo/main/ics

import os
import pandas as pd
import datetime
import calendar
import argparse

# ─── CONFIG ────────────────────────────────────────────────────────────────
TIME_SLOTS = ["9AM-11AM", "11AM-1PM", "1PM-3PM", "3PM-5PM"]

# ─── LOAD AVAILABILITY ──────────────────────────────────────────────────────

def _normalize_cols(df):
    """Lowercases, strips, and removes non-alphanum characters from column names."""
    cols = {}
    for c in df.columns:
        norm = "".join(filter(str.isalnum, c.lower()))
        cols[c] = norm
    return df.rename(columns=cols)

def _find_col(df, *keywords):
    """Finds the first column in the DataFrame that contains all keywords."""
    for col in df.columns:
        if all(kw in col for kw in keywords):
            return col
    return None

def load_availability(path):
    """
    Loads availability from an Excel file with flexible column name matching.
    """
    df_raw = pd.read_excel(path, sheet_name=0)
    df = _normalize_cols(df_raw)

    # Find columns by keywords
    first_name_col = _find_col(df, 'first', 'name')
    last_name_col = _find_col(df, 'last', 'name')
    ucid_col = _find_col(df, 'ucid')
    senior_col = _find_col(df, 'senior')

    # Dynamically find availability columns
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    avail_cols = {day: _find_col(df, day) for day in days}

    # Check for missing columns
    missing = [k for k, v in {
        'First Name': first_name_col, 'Last Name': last_name_col,
        'UCID': ucid_col, 'Senior Status': senior_col,
        **{d.capitalize(): c for d, c in avail_cols.items()}
    }.items() if not v]

    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    people = []
    for _, row in df.iterrows():
        first = row[first_name_col] if first_name_col else ''
        last = row[last_name_col] if last_name_col else ''
        name = f"{first} {last}".strip()

        ucid = str(row[ucid_col]).strip() if ucid_col else ''
        senior_raw = str(row[senior_col]).strip().lower() if senior_col else ''
        senior = senior_raw == 'yes'

        availability = {}
        for day, col_name in avail_cols.items():
            raw = row[col_name]
            slots = [] if pd.isna(raw) or not raw else [
                s.strip() for s in str(raw).split(',') if s.strip()
            ]
            availability[day.capitalize()] = set(slots)

        people.append({
            'name': name,
            'ucid': ucid,
            'senior': senior,
            'availability': availability,
            'assignments': {}
        })
    return people

# ─── WEEKLY DATES ──────────────────────────────────────────────────────────


def get_weekly_dates(month, year):
    weeks = {}
    cal = calendar.Calendar()
    for dt in cal.itermonthdates(year, month):
        if dt.month != month:
            continue
        wk = dt.isocalendar()[1]
        weeks.setdefault(wk, []).append(dt)
    return weeks

# ─── ASSIGN SLOTS ──────────────────────────────────────────────────────────


def assign_slots(people, month, year):
    cal_assign = {}
    person_assign = {p['name']: [] for p in people}
    warnings = []
    weeks = get_weekly_dates(month, year)

    for wno, dates in weeks.items():
        # reset weekly counts
        for p in people:
            p['assignments'][wno] = 0

        for dt in sorted(dates):
            if dt.weekday() >= 5:  # skip weekends
                continue
            dayname = calendar.day_name[dt.weekday()]
            cal_assign.setdefault(dt, {})

            for slot in TIME_SLOTS:
                # pick one senior
                seniors = [
                    p for p in people
                    if p['senior'] and slot in p['availability'][dayname]
                ]
                elig = [p for p in seniors if p['assignments']
                        [wno] < 2] or seniors
                if not elig:
                    warnings.append(f"No senior for {dt} {slot}")
                    assigned = []
                else:
                    sel = min(elig, key=lambda p: (
                        p['assignments'][wno], p['name']))
                    assigned = [sel]

                # fill remaining 2
                need = 3 - len(assigned)
                pool = [
                    p for p in people
                    if p not in assigned and slot in p['availability'][dayname]
                ]
                epool = [p for p in pool if p['assignments'][wno] < 2] or pool
                if len(epool) < need:
                    warnings.append(
                        f"Only {len(epool)+len(assigned)} for {dt} {slot}")
                epool.sort(key=lambda p: (p['assignments'][wno], p['name']))
                assigned += epool[:need]

                # record
                cal_assign[dt][slot] = [p['name'] for p in assigned]
                for p in assigned:
                    p['assignments'][wno] += 1
                    person_assign[p['name']].append((dt, slot))

    return cal_assign, person_assign, warnings

# ─── ICS GENERATION ────────────────────────────────────────────────────────


def write_person_ics(person_name, ucid, assignments, base_url, month, year,
                     output_dir="docs/ics"):
    import os
    import hashlib
    from datetime import datetime, timezone
    from icalendar import Calendar, Event

    # 1) hash the UCID
    h = hashlib.sha256(ucid.encode('utf-8')).hexdigest()[:8]
    fname = f"{h}.ics"

    # 2) ensure docs/ics directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ics_dir = os.path.join(script_dir, output_dir)
    os.makedirs(ics_dir, exist_ok=True)
    path = os.path.join(ics_dir, fname)

    # 3) load existing or create new VCALENDAR
    if os.path.exists(path):
        with open(path, "rb") as f:
            cal = Calendar.from_ical(f.read())
    else:
        cal = Calendar()
        cal.add('VERSION',  '2.0')
        cal.add('CALSCALE', 'GREGORIAN')
        cal.add('METHOD',   'PUBLISH')
        cal.add('PRODID',   '-//schedule-script//EN')

    # 4) remove existing events for this month/year
    to_remove = []
    for comp in cal.walk():
        if comp.name == 'VEVENT':
            dt = comp.decoded('DTSTART')
            if dt.year == year and dt.month == month:
                to_remove.append(comp)
    for comp in to_remove:
        # pull it out of the internal list
        cal.subcomponents.remove(comp)

    # 5) append new events
    for dt, slot in assignments:
        if dt.year != year or dt.month != month:
            continue

        start_h, end_h = {
            "9AM-11AM": (9, 11),
            "11AM-1PM": (11, 13),
            "1PM-3PM":  (13, 15),
            "3PM-5PM":  (15, 17),
        }[slot]

        dtstart = datetime(dt.year, dt.month, dt.day,
                           start_h, 0, 0, tzinfo=timezone.utc)
        dtend = datetime(dt.year, dt.month, dt.day,
                         end_h,  0, 0, tzinfo=timezone.utc)
        dtstamp = datetime.now(timezone.utc)

        ev = Event()
        ev.add('UID',     f"{h}-{dt.isoformat()}-{slot}@schedule")
        ev.add('DTSTAMP', dtstamp)
        ev.add('DTSTART', dtstart)
        ev.add('DTEND',   dtend)
        ev.add('SUMMARY', f"{person_name} shift ({slot})")

        cal.add_component(ev)

    # 6) write the merged calendar back out
    with open(path, "wb") as f:
        f.write(cal.to_ical())

    return f"{base_url.rstrip('/')}/{fname}"

# ─── CALENDAR SHEET ───────────────────────────────────────────────────────


def build_calendar_sheet(writer, cal_assign, month, year):
    import datetime
    import calendar
    wb = writer.book
    ws = wb.add_worksheet('Monthly Schedule')
    writer.sheets['Monthly Schedule'] = ws

    # -- Formats
    title_fmt = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'bold': True, 'font_size': 16
    })
    header_fmt = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'bold': True,
        'bg_color': '#D9D9D9', 'border': 1
    })
    date_fmt = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'bold': True, 'font_size': 12, 'border': 1
    })
    out_fmt = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'bg_color': '#A9A9A9'
    })
    cell_light = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10
    })
    cell_dark = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10, 'bg_color': '#C0C0C0'
    })
    time_light = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'bold': True, 'border': 1, 'font_size': 10
    })
    time_dark = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'bold': True, 'border': 1, 'font_size': 10, 'bg_color': '#C0C0C0'
    })

    # -- Title & Headers
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    total_cols = 1 + len(days)*2
    ws.merge_range(0, 0, 0, total_cols-1,
                   f"{calendar.month_name[month]} {year}", title_fmt)
    ws.set_row(1, 20)
    ws.set_column(0, 0, 20)  # Time-Slot col
    for i, d in enumerate(days):
        c0 = 1 + i*2
        ws.set_column(c0,   c0,   4)   # date col
        ws.set_column(c0+1, c0+1, 18)  # assignment col
        ws.merge_range(1, c0, 1, c0+1, d, header_fmt)

    # -- Grid
    cal = calendar.Calendar()
    weeks = cal.monthdays2calendar(year, month)
    row = 2
    rows_per_day = len(TIME_SLOTS)*3

    for week_idx, week in enumerate(weeks):
        start_row = row
        # week-alt for Time-Slot labels
        wk_fmt = time_dark if (week_idx % 2 == 0) else time_light

        # merge out-of-month columns
        for i, (day, _) in enumerate(week):
            c0 = 1 + i*2
            if day == 0:
                ws.merge_range(
                    start_row, c0,
                    start_row+rows_per_day-1, c0+1,
                    '', out_fmt
                )

        # merge in-month date numbers
        for i, (day, _) in enumerate(week):
            c0 = 1 + i*2
            if day != 0:
                ws.merge_range(
                    start_row, c0,
                    start_row+rows_per_day-1, c0,
                    day, date_fmt
                )

        # Time-Slot labels in col 0
        for si, slot in enumerate(TIME_SLOTS):
            r0 = start_row + si*3
            ws.merge_range(r0, 0, r0+2, 0, slot, wk_fmt)

        # Assignments alternate by slot index
        for i, (day, _) in enumerate(week):
            c1 = 1 + i*2 + 1
            if day == 0:
                continue
            dt = datetime.date(year, month, day)
            for si, slot in enumerate(TIME_SLOTS):
                names = cal_assign.get(dt, {}).get(slot, [])
                fmt = cell_light if (si % 2 == 0) else cell_dark
                for sub in range(3):
                    r = start_row + si*3 + sub
                    ws.write(r, c1, names[sub] if sub <
                             len(names) else '', fmt)

        # compact row heights
        for r in range(start_row, start_row+rows_per_day):
            ws.set_row(r, 15)

        row += rows_per_day

# ─── PERSON SHEET ──────────────────────────────────────────────────────────


def build_person_sheet(writer, person_assign, ics_links):
    import pandas as pd

    wb = writer.book
    ws = wb.add_worksheet('Person Schedule')
    writer.sheets['Person Schedule'] = ws

    # 1) Write Name and Total Shifts via DataFrame
    df = pd.DataFrame([
        {'Name': name, 'Total Shifts': len(assigns)}
        for name, assigns in person_assign.items()
    ])
    df.to_excel(writer, sheet_name='Person Schedule', index=False)

    # 2) Style header row
    hdr_fmt = wb.add_format({
        'bold': True, 'bg_color': '#D9D9D9',
        'border': 1, 'font_name': 'Arial'
    })
    for col_idx, col_name in enumerate(df.columns):
        ws.write(0, col_idx, col_name, hdr_fmt)
        ws.set_column(col_idx, col_idx, 20)

    # 3) Add Calendar URL column header
    cal_col = len(df.columns)
    ws.write(0, cal_col, 'Calendar URL', hdr_fmt)
    ws.set_column(cal_col, cal_col, 40)

    # 4) Write hyperlinks using HYPERLINK formula
    link_fmt = wb.add_format({
        'font_name': 'Arial', 'font_color': 'blue', 'underline': True
    })
    for row_idx, name in enumerate(df['Name'], start=1):
        https_url = ics_links.get(name, '')
        if not https_url:
            continue
        webcal_url = https_url.replace('https://', 'webcal://')
        formula = f'=HYPERLINK("{webcal_url}", "Subscribe")'
        ws.write_formula(row_idx, cal_col, formula, link_fmt)

# ─── LOG SHEET ─────────────────────────────────────────────────────────────


def build_log_sheet(writer, cal_assign, warnings):
    wb = writer.book
    ws = wb.add_worksheet('Log')
    writer.sheets['Log'] = ws

    rows = []
    for dt, slots in sorted(cal_assign.items()):
        if dt.weekday() >= 5:
            continue
        for slot, names in slots.items():
            rows.append({
                'Date': dt.strftime('%Y-%m-%d'),
                'Slot': slot,
                'Assigned': ', '.join(names)
            })
    df1 = pd.DataFrame(rows)
    df1.to_excel(writer, sheet_name='Log', startrow=1, index=False)

    start = len(rows)+3
    ws.write(start, 0, 'Warnings')
    df2 = pd.DataFrame([{'Warning': w} for w in warnings])
    df2.to_excel(writer, sheet_name='Log', startrow=start+1, index=False)

    fmt_hdr = wb.add_format({
        'bold': True, 'bg_color': '#D9D9D9', 'border': 1
    })
    # header for assignments and warnings
    for col in range(3):
        ws.write(
            0 if col < len(df1.columns) else start,
            col,
            df1.columns[col] if col < len(df1.columns) else 'Warnings',
            fmt_hdr
        )
    ws.set_column(0, 2, 25)

# ─── MAIN ─────────────────────────────────────────────────────────────────


def main():
    import argparse
    import pandas as pd

    p = argparse.ArgumentParser()
    p.add_argument('--input',       required=True)
    p.add_argument('--month',       type=int, required=True)
    p.add_argument('--year',        type=int, required=True)
    p.add_argument('--output',      default=None)
    p.add_argument(
        '--cal-url-base',
        required=True,
        help="Public URL base for the generated ics files"
    )
    args = p.parse_args()

    # 1) Load people (with UCID) and assign slots
    people = load_availability(args.input)
    cal_assign, person_assign, warnings = assign_slots(
        people, args.month, args.year
    )

    # 2) Write per-person ICS feeds (hashed by UCID) and collect URLs
    ics_folder = "docs/ics"
    ics_links = {}
    for p in people:
        name = p['name']
        ucid = p['ucid']
        assigns = person_assign.get(name, [])
        ics_links[name] = write_person_ics(
            name,
            ucid,
            assigns,
            args.cal_url_base,
            month=args.month,
            year=args.year,
            output_dir=ics_folder
        )

    # 3) Build and save Excel workbook
    out = args.output or f"schedule_{args.month}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        build_calendar_sheet(writer, cal_assign, args.month, args.year)
        build_person_sheet(writer, person_assign, ics_links)
        build_log_sheet(writer, cal_assign, warnings)

    # 4) Summary output
    print(f"Written schedule + logs to {out}")
    print(f".ics files in {ics_folder}, served at {
          args.cal_url_base}/<UCID_HASH>.ics")


if __name__ == '__main__':
    main()
