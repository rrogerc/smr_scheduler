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


def load_availability(path):
    df = pd.read_excel(path, sheet_name=0)
    df.columns = df.columns.str.strip()
    people = []
    for _, row in df.iterrows():
        first = row.get('First Name', row.get('First Name:', ''))
        last = row.get('Last Name',  row.get('Last Name:',  ''))
        name = f"{first} {last}".strip()
        senior = str(row.get('Are you senior?', '')).strip().lower() == 'yes'
        availability = {}
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            raw = row.get(f'When is your weekly availability? [{day}]', '')
            slots = [] if pd.isna(raw) or not raw else [
                s.strip() for s in str(raw).split(',') if s.strip()
            ]
            availability[day] = set(slots)
        people.append({
            'name': name,
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


def write_person_ics(person_name, assignments, base_url, output_dir="ics"):
    """
    Writes <output_dir>/First_Last.ics with one VEVENT per shift.
    Returns the public URL: base_url/First_Last.ics
    """
    import os
    from datetime import datetime, timezone

    os.makedirs(output_dir, exist_ok=True)
    fname = person_name.replace(" ", "_") + ".ics"
    path = os.path.join(output_dir, fname)

    # VCALENDAR header with minimal required properties
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "PRODID:-//schedule-script//EN",
    ]

    for dt, slot in assignments:
        # map slot to hours
        start_h, end_h = {
            "9AM-11AM":  (9, 11),
            "11AM-1PM":  (11, 13),
            "1PM-3PM":   (13, 15),
            "3PM-5PM":   (15, 17),
        }[slot]

        # Build timezone-aware start/end datetimes in UTC
        dtstart_dt = datetime(dt.year, dt.month, dt.day,
                              start_h, 0, 0, tzinfo=timezone.utc)
        dtend_dt = datetime(dt.year, dt.month, dt.day,
                            end_h,   0, 0, tzinfo=timezone.utc)
        dtstamp = datetime.now(timezone.utc)

        # Format as YYYYMMDDTHHMMSSZ
        dtstart = dtstart_dt.strftime("%Y%m%dT%H%M%SZ")
        dtend = dtend_dt.strftime("%Y%m%dT%H%M%SZ")
        dtstamp = dtstamp.strftime("%Y%m%dT%H%M%SZ")

        uid = f"{person_name}-{dt.isoformat()}-{slot}@schedule"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{person_name} shift ({slot})",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    # Write out the .ics file
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines))

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

    cal_assign, person_assign, warnings = assign_slots(
        load_availability(args.input),
        args.month, args.year
    )

    # write out per-person ICS and collect URLs
    ics_links = {}
    for name, assigns in person_assign.items():
        ics_links[name] = write_person_ics(
            name, assigns, args.cal_url_base
        )

    out = args.output or f"schedule_{args.month}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        build_calendar_sheet(writer, cal_assign, args.month, args.year)
        build_person_sheet(writer, person_assign, ics_links)
        build_log_sheet(writer, cal_assign, warnings)

    print(f"Written schedule + logs to {out}")
    print(f".ics files in ./ics/, served at {args.cal_url_base}/<Name>.ics")


if __name__ == '__main__':
    main()
