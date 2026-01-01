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
import collections

# ─── CONFIG ────────────────────────────────────────────────────────────────
TIME_SLOTS = ["8AM-10AM", "10AM-12PM", "12PM-2PM", "2PM-4PM", "4PM-6PM"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ─── MAX FLOW SOLVER (Edmonds-Karp) ────────────────────────────────────
class FlowSolver:
    def __init__(self):
        self.graph = collections.defaultdict(dict) # u -> v -> capacity
        self.flow = collections.defaultdict(dict)  # u -> v -> flow
        
    def add_edge(self, u, v, cap):
        # Directed edge u->v with capacity
        # If edge exists, add to capacity
        self.graph[u][v] = self.graph[u].get(v, 0) + cap
        self.graph[v][u] = self.graph[v].get(u, 0) + 0 # Residual edge
        
        # Initialize flow
        if v not in self.flow[u]: self.flow[u][v] = 0
        if u not in self.flow[v]: self.flow[v][u] = 0

    def bfs(self, s, t, parent):
        visited = {s}
        queue = collections.deque([s])
        
        while queue:
            u = queue.popleft()
            if u == t:
                return True
            
            for v, cap in self.graph[u].items():
                # Check residual capacity
                if v not in visited and cap - self.flow[u][v] > 0:
                    visited.add(v)
                    parent[v] = u
                    queue.append(v)
        return False

    def max_flow(self, s, t):
        max_f = 0
        while True:
            parent = {}
            if not self.bfs(s, t, parent):
                break
            
            # Find path flow
            path_flow = float('inf')
            v = t
            while v != s:
                u = parent[v]
                path_flow = min(path_flow, self.graph[u][v] - self.flow[u][v])
                v = u
            
            # Update residual capacities
            v = t
            while v != s:
                u = parent[v]
                self.flow[u][v] += path_flow
                self.flow[v][u] -= path_flow
                v = u
                
            max_f += path_flow
        return max_f

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
    avail_cols = {day.lower(): _find_col(df, day.lower()) for day in DAYS_OF_WEEK}

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
        })
    # Deduplicate by UCID (keep last occurrence)
    unique_people = {}
    for p in people:
        key = p['ucid'] if p['ucid'] else p['name']
        unique_people[key] = p
    
    return list(unique_people.values())

# ─── GENERATE MASTER TEMPLATE ──────────────────────────────────────────────

def solve_weekly_template(people):
    """
    Generates a single static weekly schedule (Mon-Fri) using Max Flow.
    Returns a dict: { 'Monday': { '8AM-10AM': [names], ... }, ... }
    """
    print("  > Generating Master Weekly Template (Mon-Fri)...")
    
    # Initialize Template
    template = {day: {slot: [] for slot in TIME_SLOTS} for day in DAYS_OF_WEEK}
    
    # Helper to count shifts in the current template
    # Keyed by UCID to ensure uniqueness
    person_counts = collections.defaultdict(int)

    def run_flow_phase(target_group_filter, slot_cap_fn, description):
        solver = FlowSolver()
        SOURCE = "SOURCE"
        SINK = "SINK"

        active_people = [p for p in people if target_group_filter(p)]
        
        # Build Graph
        for p in active_people:
            name = p['name']
            uid = p['ucid'] if p['ucid'] else name
            
            current_shifts = person_counts[uid]
            remaining_quota = 2 - current_shifts
            
            if remaining_quota <= 0:
                continue

            # Edge: SOURCE -> PERSON (Capacity: remaining quota)
            person_node = f"PERSON_{uid}"
            solver.add_edge(SOURCE, person_node, remaining_quota)

            for day in DAYS_OF_WEEK:
                for slot in TIME_SLOTS:
                    # Check Availability
                    if slot not in p['availability'].get(day, []):
                        continue
                    
                    # Prevent double-booking the EXACT SAME slot across phases
                    if name in template[day][slot]:
                        continue

                    # Check Senior Limit (Max 2 seniors per slot)
                    current_seniors_in_slot = len([
                        x for x in template[day][slot] 
                        if any(sp['name'] == x and sp['senior'] for sp in people)
                    ])
                    if p['senior'] and current_seniors_in_slot >= 2:
                        continue
                    
                    # Check Slot Capacity for this Phase
                    curr_total = len(template[day][slot])
                    cap = slot_cap_fn(day, slot, curr_total)
                    
                    if cap > 0:
                        slot_node = f"SLOT_{day}_{slot}"
                        # Edge: PERSON -> SLOT (Capacity 1)
                        # This allows multiple slots per day as long as total matches quota
                        solver.add_edge(person_node, slot_node, 1)

        # Connect Slots to Sink
        for day in DAYS_OF_WEEK:
            for slot in TIME_SLOTS:
                curr_total = len(template[day][slot])
                cap = slot_cap_fn(day, slot, curr_total)
                if cap > 0:
                    slot_node = f"SLOT_{day}_{slot}"
                    solver.add_edge(slot_node, SINK, cap)

        # Solve
        max_f = solver.max_flow(SOURCE, SINK)
        
        # Commit Assignments
        assigned_count = 0
        for p in active_people:
            name = p['name']
            uid = p['ucid'] if p['ucid'] else name
            person_node = f"PERSON_{uid}"
            
            if person_node not in solver.flow: continue
            
            # Trace flow: PERSON -> SLOT
            for slot_node, flow_val in solver.flow[person_node].items():
                if flow_val > 0 and slot_node.startswith("SLOT_"):
                    # Found assignment
                    parts = slot_node.split('_')
                    day = parts[1]
                    slot = parts[2]
                    
                    template[day][slot].append(name)
                    person_counts[uid] += 1
                    assigned_count += 1
                            
        print(f"    - {description}: Assigned {assigned_count} shifts.")

    # ─── PHASES ───

    # Phase 1: Senior Spread (Ensure at least 1 senior where possible)
    def cap_phase1(day, slot, curr):
        return 1 if curr == 0 else 0
    run_flow_phase(lambda p: p['senior'], cap_phase1, "Phase 1 (Senior Spread)")

    # Phase 2: Senior Depth (Allow up to 2 seniors)
    def cap_phase2(day, slot, curr):
        return 2 - curr if curr < 2 else 0
    run_flow_phase(lambda p: p['senior'], cap_phase2, "Phase 2 (Senior Max)")

    # Phase 3: General Fill (Fill up to 5 people)
    for target_cap in range(1, 6):
        def cap_phase_general(day, slot, curr):
            if curr >= target_cap:
                return 0
            return target_cap - curr
        run_flow_phase(lambda p: True, cap_phase_general, f"Phase 3 (General Fill - Cap {target_cap})")

    # Generate Warnings for the Template
    warnings = []
    for p in people:
        name = p['name']
        uid = p['ucid'] if p['ucid'] else name
        if person_counts[uid] < 2:
            warnings.append(f"{name} has only {person_counts[uid]} shifts in the weekly template.")
            
    for day in DAYS_OF_WEEK:
        for slot in TIME_SLOTS:
            assigned = template[day][slot]
            has_senior = any(x for x in assigned if any(p['name'] == x and p['senior'] for p in people))
            if assigned and not has_senior:
                warnings.append(f"{day} {slot} has {len(assigned)} people but NO SENIOR.")

    return template, warnings

# ─── APPLY TEMPLATE TO CALENDAR ────────────────────────────────────────────

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

def apply_schedule_to_month(template, month, year):
    """
    Expands the generic weekly template onto specific dates for a month.
    """
    dates = get_month_dates(month, year)
    cal_assign = {} # dt -> { slot: [names] }
    person_assign = collections.defaultdict(list) # name -> [(dt, slot)]
    
    for dt in dates:
        day_name = calendar.day_name[dt.weekday()] # e.g., "Monday"
        day_schedule = template.get(day_name, {})
        
        cal_assign[dt] = {}
        
        for slot, names in day_schedule.items():
            cal_assign[dt][slot] = list(names) # Copy list
            for name in names:
                person_assign[name].append((dt, slot))
                
    return cal_assign, person_assign

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
            "8AM-10AM":  (8, 10),
            "10AM-12PM": (10, 12),
            "12PM-2PM":  (12, 14),
            "2PM-4PM":   (14, 16),
            "4PM-6PM":   (16, 18),
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


def build_calendar_sheet(writer, cal_assign, month, year, people, sheet_name=None):
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
    # Senior formats (Bold + Blue text)
    senior_light = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10, 'bold': True, 'font_color': 'blue'
    })
    senior_dark = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10, 'bg_color': '#C0C0C0', 'bold': True, 'font_color': 'blue'
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
    # Increase rows per day since we have up to 5 people
    names_per_slot = 5
    rows_per_day = len(TIME_SLOTS) * names_per_slot

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
            r0 = start_row + si*names_per_slot
            ws.merge_range(r0, 0, r0+names_per_slot-1, 0, slot, wk_fmt)

        # Assignments - Week + Slot alternating pattern
        # (week_idx + si) % 2 ensures slots alternate within a week, 
        # and the pattern flips every week to distinguish week boundaries.
        for i, (day, _) in enumerate(week):
            c1 = 1 + i*2 + 1
            if day == 0:
                continue
            dt = datetime.date(year, month, day)
            for si, slot in enumerate(TIME_SLOTS):
                names = cal_assign.get(dt, {}).get(slot, [])
                
                # Logic: Alternate by week index AND slot index
                is_light = (week_idx + si) % 2 == 0
                
                for sub in range(names_per_slot):
                    r = start_row + si*names_per_slot + sub
                    
                    if sub < len(names):
                        name = names[sub]
                        is_senior = any(p['senior'] for p in people if p['name'] == name)
                        
                        if is_light:
                            fmt = senior_light if is_senior else cell_light
                        else:
                            fmt = senior_dark if is_senior else cell_dark
                            
                        ws.write(r, c1, name, fmt)
                    else:
                        # Empty cell
                        fmt = cell_light if is_light else cell_dark
                        ws.write(r, c1, '', fmt)

        # compact row heights
        for r in range(start_row, start_row+rows_per_day):
            ws.set_row(r, 15)

        row += rows_per_day

# ─── PERSON SHEET ──────────────────────────────────────────────────────────


def build_person_sheet(writer, person_assign, ics_links, months):
    import pandas as pd

    wb = writer.book
    ws = wb.add_worksheet('Shift Count')
    writer.sheets['Shift Count'] = ws

    # Prepare data rows
    data = []
    for name, assigns in person_assign.items():
        row = {'Name': name, 'Total Shifts': len(assigns)}
        # Add columns for each month
        for m in months:
            m_name = calendar.month_name[m]
            count = len([dt for dt, _ in assigns if dt.month == m])
            row[m_name] = count
        data.append(row)

    df = pd.DataFrame(data)
    
    # Reorder columns: Name, [Month1, Month2...], Total Shifts
    cols = ['Name'] + [calendar.month_name[m] for m in months] + ['Total Shifts']
    
    # Ensure all columns exist (in case no one worked a specific month)
    for c in cols:
        if c not in df.columns:
            df[c] = 0
            
    df = df[cols] # Reorder
    
    df.to_excel(writer, sheet_name='Shift Count', index=False)

    # 2) Style header row
    hdr_fmt = wb.add_format({
        'bold': True, 'bg_color': '#D9D9D9',
        'border': 1, 'font_name': 'Arial'
    })
    for col_idx, col_name in enumerate(df.columns):
        ws.write(0, col_idx, col_name, hdr_fmt)
        ws.set_column(col_idx, col_idx, 15 if col_idx > 0 else 20)

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

# ─── WARNINGS SHEET ─────────────────────────────────────────────────────────────


def build_log_sheet(writer, warnings):
    wb = writer.book
    ws = wb.add_worksheet('Warnings')
    writer.sheets['Warnings'] = ws

    # Add generation timestamp
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " MST"
    ws.write(0, 0, f"Generated On: {now}")

    df2 = pd.DataFrame([{'Warning': w} for w in warnings])
    df2.to_excel(writer, sheet_name='Warnings', startrow=2, index=False)

    fmt_hdr = wb.add_format({
        'bold': True, 'bg_color': '#D9D9D9', 'border': 1
    })
    # header for warnings
    ws.write(2, 0, 'Warnings', fmt_hdr)
    ws.set_column(0, 0, 80)

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
    
    # 2) Generate the MASTER WEEKLY TEMPLATE
    # This solves the schedule for one ideal week (Mon-Fri)
    template, warnings = solve_weekly_template(people)

    # Aggregated results for output
    all_cal_assign = {}
    all_person_assign = collections.defaultdict(list) # name -> [(dt, slot)]

    for m in months:
        print(f"Applying template to {calendar.month_name[m]} {args.year}...")
        cal_assign, person_assign = apply_schedule_to_month(template, m, args.year)
        
        # Merge cal_assign
        all_cal_assign.update(cal_assign)
        
        # Merge person_assign
        for name, assigns in person_assign.items():
            all_person_assign[name].extend(assigns)

    # 3) Write per-person ICS feeds (hashed by UCID) and collect URLs
    ics_folder = "docs/ics"
    ics_links = {}
    
    for p in people:
        name = p['name']
        ucid = p['ucid']
        assigns = all_person_assign.get(name, [])
        
        ics_links[name] = write_person_ics(
            name,
            ucid,
            assigns,
            args.cal_url_base,
            months=months,
            year=args.year,
            output_dir=ics_folder
        )

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
            build_calendar_sheet(writer, month_cal_assign, m, args.year, people, sheet_name=sheet_name)
        
        # Summary sheets
        build_person_sheet(writer, all_person_assign, ics_links, months)
        build_log_sheet(writer, warnings)

    # 5) Summary output
    print(f"Written {args.term} term schedule + logs to {out}")
    print(f".ics files in {ics_folder}, served at {args.cal_url_base}/<UCID_HASH>.ics")


if __name__ == '__main__':
    main()