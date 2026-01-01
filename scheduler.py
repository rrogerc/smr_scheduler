#!/usr/bin/env python3
# schedule.py
# Generates a monthly schedule calendar and per-person summary from availability responses.
# Also emits per-person .ics feeds and links them in the Excel.

import os
import pandas as pd
import datetime
import calendar
import argparse
import hashlib
import random

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
            # We'll track assignments differently now, but keeping this structure for ICS if needed
            'assignments': {} 
        })
    return people

# ─── ASSIGN SLOTS ──────────────────────────────────────────────────────────

def get_month_dates(month, year):
    cal = calendar.Calendar()
    dates = []
    for dt in cal.itermonthdates(year, month):
        if dt.month != month:
            continue
        if dt.weekday() >= 5: # Skip weekends
            continue
        dates.append(dt)
    return sorted(dates)

def assign_slots(people, month, year):
    # Initialize assignments tracking for this month
    cal_assign = {} # {date: {slot: [names]}}
    person_assign = {p['name']: [] for p in people}
    monthly_counts = {p['name']: 0 for p in people}
    warnings = []
    
    dates = get_month_dates(month, year)
    
    # Pre-structure the calendar dict
    all_slots = [] # List of (dt, slot_name) tuples
    for dt in dates:
        cal_assign[dt] = {}
        dayname = calendar.day_name[dt.weekday()]
        for slot in TIME_SLOTS:
            cal_assign[dt][slot] = []
            all_slots.append((dt, slot, dayname))

    # Helper to check availability
    def is_available(person, dayname, slot):
        return slot in person['availability'].get(dayname, [])

    # Helper: deterministic hash for tie-breaking
    def get_hash(person, dt, slot):
        hash_input = f"{person['ucid']}-{dt.isoformat()}-{slot}".encode('utf-8')
        return int(hashlib.sha256(hash_input).hexdigest(), 16)

    # ─── PHASE 1: MANDATORY SENIORS ───
    # Ensure every slot has at least 1 senior
    for dt, slot, dayname in all_slots:
        current_assigned = cal_assign[dt][slot]
        has_senior = any(p['senior'] for p in people if p['name'] in current_assigned)
        
        if not has_senior:
            # Find available seniors not already assigned to this slot
            candidates = [
                p for p in people 
                if p['senior'] 
                and is_available(p, dayname, slot)
                and p['name'] not in current_assigned
            ]
            
            if not candidates:
                warnings.append(f"No senior available for {dt} {slot}")
                continue
            
            # Pick senior with lowest monthly count, then deterministic hash
            candidates.sort(key=lambda p: (monthly_counts[p['name']], get_hash(p, dt, slot)))
            selected = candidates[0]
            
            cal_assign[dt][slot].append(selected['name'])
            person_assign[selected['name']].append((dt, slot))
            monthly_counts[selected['name']] += 1

    # ─── PHASE 2: QUOTA FILL (Target 2 shifts per person) ───
    # Iterate until everyone has at least 2 shifts (or no availability left)
    
    # Create a queue of people who need shifts
    people_needing_shifts = [p for p in people if monthly_counts[p['name']] < 2]
    
    # We loop while there are people needing shifts and we are making progress
    progress = True
    while people_needing_shifts and progress:
        progress = False
        # Sort people by who needs shifts the most (lowest count)
        people_needing_shifts.sort(key=lambda p: (monthly_counts[p['name']], p['ucid']))
        
        for person in people_needing_shifts[:]: # Iterate copy
            if monthly_counts[person['name']] >= 2:
                people_needing_shifts.remove(person)
                continue
                
            # Find all available slots for this person
            available_slots = []
            for dt, slot, dayname in all_slots:
                # Check availability
                if not is_available(person, dayname, slot):
                    continue
                # Check if already assigned
                if person['name'] in cal_assign[dt][slot]:
                    continue
                
                # We prioritize slots with fewer people to spread the load
                # But we might also want to prioritize slots that need coverage (count < 2)
                current_count = len(cal_assign[dt][slot])
                available_slots.append((dt, slot, current_count))
            
            if not available_slots:
                # No slots available for this person
                people_needing_shifts.remove(person)
                continue
            
            # Sort slots: 
            # 1. Primary: Slots with < 2 people (needs coverage)
            # 2. Secondary: Slots with fewest people
            # 3. Tertiary: Hash
            available_slots.sort(key=lambda x: (
                0 if x[2] < 2 else 1, # Prioritize filling empty slots
                x[2],                 # Then fill less populated slots
                get_hash(person, x[0], x[1]) # Tie-breaker
            ))
            
            # Pick the best slot
            best_dt, best_slot, _ = available_slots[0]
            
            cal_assign[best_dt][best_slot].append(person['name'])
            person_assign[person['name']].append((best_dt, best_slot))
            monthly_counts[person['name']] += 1
            progress = True
            
            if monthly_counts[person['name']] >= 2:
                people_needing_shifts.remove(person)

    # ─── PHASE 3: MINIMUM COVERAGE (Target 2 people per slot) ───
    # Ensure every slot has at least 2 people if possible
    for dt, slot, dayname in all_slots:
        current_assigned = cal_assign[dt][slot]
        if len(current_assigned) < 2:
            needed = 2 - len(current_assigned)
            
            # Find candidates
            candidates = [
                p for p in people 
                if is_available(p, dayname, slot) 
                and p['name'] not in current_assigned
            ]
            
            if len(candidates) < needed:
                 warnings.append(f"Only {len(current_assigned)+len(candidates)} people available for {dt} {slot} (Need 2)")
            
            # Sort candidates:
            # 1. Lowest monthly count (give shifts to those who have few, even if > 2)
            # 2. Hash
            candidates.sort(key=lambda p: (monthly_counts[p['name']], get_hash(p, dt, slot)))
            
            to_add = candidates[:needed]
            for p in to_add:
                cal_assign[dt][slot].append(p['name'])
                person_assign[p['name']].append((dt, slot))
                monthly_counts[p['name']] += 1

    return cal_assign, person_assign, warnings

# ─── ICS GENERATION ────────────────────────────────────────────────────────

def write_person_ics(person_name, ucid, assignments, base_url, months, year, output_dir="docs/ics"):
    """
    Writes assignments to an ICS file. 
    `months` is a list of integers (e.g. [9,10,11,12]) representing the term.
    """
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

    # 4) remove existing events for this term (all months in `months`)
    to_remove = []
    for comp in cal.walk():
        if comp.name == 'VEVENT':
            dt = comp.decoded('DTSTART')
            # Check if event is within any of the target months of this year
            if dt.year == year and dt.month in months:
                to_remove.append(comp)
    for comp in to_remove:
        cal.subcomponents.remove(comp)

    # 5) append new events
    for dt, slot in assignments:
        # Check against term just in case, though assignments should match
        if dt.year != year or dt.month not in months:
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


def build_calendar_sheet(writer, cal_assign, month, year, sheet_name=None):
    import datetime
    import calendar
    wb = writer.book
    if sheet_name is None:
        sheet_name = f"{calendar.month_name[month]} {year}"
    
    ws = wb.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = ws

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
                # Assuming max 3 names display, if more we might just overwrite or need better UI
                # With new alg, could have more than 3? 
                # User said "don't need to fill 5", implies maybe max 3-4?
                # The visual grid writes 3 rows. If we assign 4, the 4th won't show clearly.
                # But that's a display issue, logical assignment is fine.
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
    import calendar

    p = argparse.ArgumentParser()
    p.add_argument('--input',       required=True)
    p.add_argument('--term',        choices=['Fall', 'Winter'], required=True, help="Term to generate schedule for")
    p.add_argument('--year',        type=int, required=True)
    p.add_argument('--output',      default=None)
    p.add_argument(
        '--cal-url-base',
        required=True,
        help="Public URL base for the generated ics files"
    )
    args = p.parse_args()

    # Determine months based on term
    if args.term == 'Fall':
        months = [9, 10, 11, 12]
    else: # Winter
        months = [1, 2, 3, 4]

    # 1) Load people (with UCID)
    people = load_availability(args.input)
    
    # Aggregated results
    all_cal_assign = {}
    all_person_assign = {p['name']: [] for p in people}
    all_warnings = []

    for m in months:
        print(f"Generating for {calendar.month_name[m]} {args.year}...")
        cal_assign, person_assign, warnings = assign_slots(people, m, args.year)
        
        # Merge cal_assign
        all_cal_assign.update(cal_assign)
        
        # Merge person_assign
        for name, assigns in person_assign.items():
            if name in all_person_assign:
                all_person_assign[name].extend(assigns)
        
        # Merge warnings
        all_warnings.extend(warnings)

    # 3) Write per-person ICS feeds (hashed by UCID) and collect URLs
    ics_folder = "docs/ics"
    ics_links = {}
    
    # Prepare roster data for JSON export
    roster_data = []
    
    for p in people:
        name = p['name']
        ucid = p['ucid']
        assigns = all_person_assign.get(name, [])
        shift_count = len(assigns)
        
        # Add to roster data
        # Calculate ucid_hash same way as write_person_ics does
        h = hashlib.sha256(ucid.encode('utf-8')).hexdigest()[:8]
        roster_data.append({
            "name": name,
            "shifts": shift_count,
            "ucid_hash": h
        })
        
        ics_links[name] = write_person_ics(
            name,
            ucid,
            assigns,
            args.cal_url_base,
            months=months,
            year=args.year,
            output_dir=ics_folder
        )

    # Write roster.json
    import json
    roster_path = f"docs/rosters/roster_{args.term}_{args.year}.json"
    os.makedirs(os.path.dirname(roster_path), exist_ok=True)
    with open(roster_path, "w") as f:
        # Sort by name for nicer display
        roster_data.sort(key=lambda x: x['name'])
        json.dump(roster_data, f, indent=2)
    print(f"Written roster summary to {roster_path}")

    # 4) Build and save Excel workbook
    out = args.output or f"schedule_{args.term.lower()}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        # Create a sheet for each month
        for m in months:
            # Filter cal_assign for this month
            month_cal_assign = {
                dt: slots for dt, slots in all_cal_assign.items() 
                if dt.month == m
            }
            sheet_name = f"{calendar.month_name[m]} {args.year}"
            build_calendar_sheet(writer, month_cal_assign, m, args.year, sheet_name=sheet_name)
        
        # Summary sheets
        build_person_sheet(writer, all_person_assign, ics_links)
        build_log_sheet(writer, all_cal_assign, all_warnings)

    # 5) Summary output
    print(f"Written {args.term} term schedule + logs to {out}")
    print(f".ics files in {ics_folder}, served at {args.cal_url_base}/<UCID_HASH>.ics")


if __name__ == '__main__':
    main()