# schedule.py
# Generates a monthly schedule calendar and per-person summary from availability responses.
# Writes calendar, person schedule, and detailed logs (assignments + warnings) to Excel with styled formatting.
# Usage: python schedule.py --input availability.xlsx --month 5 --year 2025 --output schedule_may_2025.xlsx

import pandas as pd
import datetime
import calendar
import argparse

# Scheduling algorithm:
# Greedy weekly balanced assignment. For each ISO week in the month:
#  - Track per-person assignment count (cap aimed at 2/week).
#  - For each weekday date and each time slot:
#    * Assign 1 senior with fewest assigns.
#    * Assign remaining 2 staff with fewest assigns.
#    * Log warnings if staffing incomplete.

TIME_SLOTS = ["9AM-11AM", "11AM-1PM", "1PM-3PM", "3PM-5PM"]


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
            slots = [] if pd.isna(raw) or not raw else [s.strip()
                                                        for s in str(raw).split(',') if s.strip()]
            availability[day] = set(slots)
        people.append({'name': name, 'senior': senior,
                      'availability': availability, 'assignments': {}})
    return people


def get_weekly_dates(month, year):
    weeks = {}
    cal = calendar.Calendar()
    for dt in cal.itermonthdates(year, month):
        if dt.month != month:
            continue
        wk = dt.isocalendar()[1]
        weeks.setdefault(wk, []).append(dt)
    return weeks


def assign_slots(people, month, year):
    cal_assign = {}
    person_assign = {p['name']: [] for p in people}
    warnings = []
    weeks = get_weekly_dates(month, year)
    for wno, dates in weeks.items():
        for p in people:
            p['assignments'][wno] = 0
        for dt in sorted(dates):
            # skip weekends
            if dt.weekday() >= 5:
                continue
            dayname = calendar.day_name[dt.weekday()]
            cal_assign.setdefault(dt, {})
            for slot in TIME_SLOTS:
                # pick senior
                seniors = [p for p in people if p['senior']
                           and slot in p['availability'][dayname]]
                elig = [p for p in seniors if p['assignments']
                        [wno] < 2] or seniors
                if not elig:
                    warnings.append(f"No senior for {dt} {slot}")
                    assigned = []
                else:
                    sel = min(elig, key=lambda p: (
                        p['assignments'][wno], p['name']))
                    assigned = [sel]
                # fill others
                need = 3-len(assigned)
                pool = [
                    p for p in people if p not in assigned and slot in p['availability'][dayname]]
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


def build_calendar_sheet(writer, cal_assign, month, year):
    import datetime
    import calendar

    wb = writer.book
    ws = wb.add_worksheet('Monthly Schedule')
    writer.sheets['Monthly Schedule'] = ws

    # ─── Formats (all Arial) ────────────────────────────────────────────────
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
    cell_fmt_light = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10
    })
    cell_fmt_dark = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'border': 1, 'font_size': 10, 'bg_color': '#F2F2F2'
    })
    time_fmt_light = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'bold': True, 'border': 1, 'font_size': 10
    })
    time_fmt_dark = wb.add_format({
        'font_name': 'Arial', 'align': 'center', 'valign': 'vcenter',
        'bold': True, 'border': 1, 'font_size': 10, 'bg_color': '#F2F2F2'
    })

    # ─── Title Row ────────────────────────────────────────────────────────────
    month_name = calendar.month_name[month]
    ws.merge_range(0, 0, 0, 8, f"{month_name} {year}", title_fmt)

    # ─── Headers ──────────────────────────────────────────────────────────────
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    ws.write(1, 0, "Time Slot", header_fmt)
    ws.set_column(0, 0, 15)
    for idx, day in enumerate(days):
        ws.write(1, idx + 1, day, header_fmt)
        ws.set_column(idx + 1, idx + 1, 18)

    # ─── Calendar Grid ───────────────────────────────────────────────────────
    cal = calendar.Calendar()
    weeks = cal.monthdays2calendar(year, month)
    row = 2

    for week in weeks:
        # 1) Day-number row
        for c, (day, wd) in enumerate(week):
            if day == 0:
                ws.write_blank(row, c + 1, '', cell_fmt_light)
            else:
                ws.write(row, c + 1, day, date_fmt)
        ws.set_row(row, 24)   # taller for date prominence
        row += 1

        # 2) For each time slot: merged label + three centered name rows
        for slot_idx, slot in enumerate(TIME_SLOTS):
            # pick light/dark for alternating blocks
            time_fmt = time_fmt_light if slot_idx % 2 == 0 else time_fmt_dark
            cell_fmt = cell_fmt_light if slot_idx % 2 == 0 else cell_fmt_dark

            # slot label merged down 3 rows in col A
            ws.merge_range(row, 0, row + 2, 0, slot, time_fmt)

            for sub in range(3):
                for c, (day, wd) in enumerate(week):
                    if day == 0:
                        ws.write_blank(row, c + 1, '', cell_fmt)
                    else:
                        dt = datetime.date(year, month, day)
                        names = cal_assign.get(dt, {}).get(slot, [])
                        name = names[sub] if sub < len(names) else ''
                        ws.write(row, c + 1, name, cell_fmt)
                ws.set_row(row, 15)  # shorter row for names
                row += 1


def build_person_sheet(writer, person_assign):
    wb = writer.book
    ws = wb.add_worksheet('Person Schedule')
    df = pd.DataFrame([
        {'Name': name, 'Total Shifts': len(a), 'Assignments': "; ".join(
            f"{d.strftime('%Y-%m-%d')} {s}" for d, s in a)}
        for name, a in person_assign.items()
    ])
    df.to_excel(writer, sheet_name='Person Schedule', index=False)
    # optional: style header
    hdr_fmt = wb.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
    for col in range(len(df.columns)):
        ws.write(0, col, df.columns[col], hdr_fmt)
        ws.set_column(col, col, 30)


def build_log_sheet(writer, cal_assign, warnings):
    wb = writer.book
    ws = wb.add_worksheet('Log')
    writer.sheets['Log'] = ws
    # Logs: assignments
    rows = []
    for dt, slots in sorted(cal_assign.items()):
        if dt.weekday() >= 5:
            continue
        for slot, names in slots.items():
            rows.append({'Date': dt.strftime('%Y-%m-%d'),
                        'Slot': slot, 'Assigned': ', '.join(names)})
    df1 = pd.DataFrame(rows)
    df1.to_excel(writer, sheet_name='Log', startrow=1, index=False)
    # Warnings
    start = len(rows)+3
    ws.write(start, 0, 'Warnings')
    df2 = pd.DataFrame([{'Warning': w} for w in warnings])
    df2.to_excel(writer, sheet_name='Log', startrow=start+1, index=False)
    # formatting
    fmt_hdr = wb.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
    for col in range(3):
        ws.write(0 if col < len(df1.columns) else start, col,
                 df1.columns[col] if col < len(df1.columns) else 'Warnings', fmt_hdr)
    ws.set_column(0, 2, 25)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--month', type=int, required=True)
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--output', default=None)
    args = p.parse_args()
    cal_assign, person_assign, warnings = assign_slots(
        load_availability(args.input), args.month, args.year)
    out = args.output or f"schedule_{args.month}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        build_calendar_sheet(writer, cal_assign, args.month, args.year)
        build_person_sheet(writer, person_assign)
        build_log_sheet(writer, cal_assign, warnings)
    print(f"Written schedule + logs to {out}")


if __name__ == '__main__':
    main()
