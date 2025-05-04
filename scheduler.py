# schedule.py
# Generates a monthly schedule calendar and per-person summary from availability responses.
# Writes calendar, person schedule, and detailed logs (assignments + warnings) to Excel.
# Usage: python schedule.py --input availability.xlsx --month 5 --year 2025 --output schedule_may_2025.xlsx

import pandas as pd
import datetime
import calendar
import argparse

# Scheduling algorithm:
# Greedy weekly balanced assignment. For each ISO week in the month:
#  - Track per-person assignment count (cap aimed at 2 per week).
#  - For each weekday date and each time slot (9-11, 11-1, 1-3, 3-5):
#    * Assign 1 senior with the fewest assignments so far in the week.
#    * Assign remaining (2) from all available staff with fewest assignments.
#    * If no eligible senior (or insufficient staff), relax weekly cap; if still none, log a warning.
#    * Respect individual availability per weekday and slot.

TIME_SLOTS = ["9AM-11AM", "11AM-1PM", "1PM-3PM", "3PM-5PM"]


def load_availability(path):
    df = pd.read_excel(path, sheet_name=0)
    df.columns = df.columns.str.strip()
    people = []
    for _, row in df.iterrows():
        first = row.get('First Name', row.get('First Name:', ''))
        last = row.get('Last Name', row.get('Last Name:', ''))
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
    calendar_assign = {}
    person_assignments = {p['name']: [] for p in people}
    warnings = []
    weeks = get_weekly_dates(month, year)
    for week_no, dates in weeks.items():
        for p in people:
            p['assignments'][week_no] = 0
        for date in sorted(dates):
            # Only assign on weekdays
            if date.weekday() >= 5:
                continue
            weekday = calendar.day_name[date.weekday()]
            calendar_assign.setdefault(date, {})
            for slot in TIME_SLOTS:
                # Choose senior
                seniors = [p for p in people if p['senior']
                           and slot in p['availability'].get(weekday, [])]
                eligible = [
                    p for p in seniors if p['assignments'][week_no] < 2]
                if not eligible:
                    eligible = seniors
                if not eligible:
                    warnings.append(f"No senior available for {date} {slot}")
                    assigned = []
                else:
                    sel = min(eligible, key=lambda p: (
                        p['assignments'][week_no], p['name']))
                    assigned = [sel]
                # Fill remaining
                needed = 3 - len(assigned)
                pool = [p for p in people if p not in assigned and slot in p['availability'].get(
                    weekday, [])]
                eligible_pool = [
                    p for p in pool if p['assignments'][week_no] < 2]
                if len(eligible_pool) < needed:
                    eligible_pool = pool
                if len(eligible_pool) < needed:
                    warnings.append(
                        f"Only {len(eligible_pool)+len(assigned)} assigned for {date} {slot}")
                eligible_pool.sort(key=lambda p: (
                    p['assignments'][week_no], p['name']))
                assigned += eligible_pool[:needed]
                # Record
                calendar_assign[date][slot] = [p['name'] for p in assigned]
                for p in assigned:
                    p['assignments'][week_no] += 1
                    person_assignments[p['name']].append((date, slot))
    return calendar_assign, person_assignments, warnings


def build_calendar_sheet(writer, calendar_assign, month, year):
    cal = calendar.Calendar()
    month_name = calendar.month_name[month]
    weeks = cal.monthdays2calendar(year, month)
    rows = []
    for week in weeks:
        # date row
        rows.append([str(day) if day != 0 else '' for day, wd in week])
        # slot rows
        for slot in TIME_SLOTS:
            rows.append([
                f"{slot}: {', '.join(calendar_assign.get(
                    datetime.date(year, month, day), {}).get(slot, []))}"
                if day != 0 and wd < 5 else '' for day, wd in week
            ])
    df = pd.DataFrame(
        rows, columns=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
    ws = writer.book.add_worksheet('Monthly Schedule')
    writer.sheets['Monthly Schedule'] = ws
    ws.merge_range(0, 0, 0, 6, f"{month_name} {year}")
    for c, d in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']):
        ws.write(1, c, d)
    for r, row in enumerate(rows, 2):
        for c, val in enumerate(row):
            ws.write(r, c, val)
    ws.set_default_row(30)
    for c in range(7):
        ws.set_column(c, c, 20)


def build_person_sheet(writer, person_assignments):
    dfp = pd.DataFrame([
        {'Name': name, 'Total Shifts': len(a), 'Assignments': "; ".join(
            f"{d.strftime('%Y-%m-%d')} {s}" for d, s in a)}
        for name, a in person_assignments.items()
    ])
    dfp.to_excel(writer, sheet_name='Person Schedule', index=False)


def build_log_sheet(writer, calendar_assign, warnings):
    # Flatten assignment summary, excluding weekends
    assign_rows = []
    for date, slots in sorted(calendar_assign.items()):
        if date.weekday() >= 5:  # skip Saturday & Sunday
            continue
        for slot, names in slots.items():
            assign_rows.append({
                'Date': date.strftime('%Y-%m-%d'),
                'Slot': slot,
                'Assigned': ', '.join(names)
            })
    dfa = pd.DataFrame(assign_rows)
    dfw = pd.DataFrame([{'Warning': w} for w in warnings])
    ws = writer.book.add_worksheet('Log')
    writer.sheets['Log'] = ws
    ws.write(0, 0, 'Assignment Summary')
    dfa.to_excel(writer, sheet_name='Log', startrow=1, index=False)
    start = len(dfa) + 3
    ws.write(start, 0, 'Warnings')
    dfw.to_excel(writer, sheet_name='Log', startrow=start+1, index=False)
    ws.set_column(0, 2, 25)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--month', type=int, required=True)
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--output', default=None)
    args = p.parse_args()
    cal, pa, w = assign_slots(load_availability(
        args.input), args.month, args.year)
    out = args.output or f"schedule_{args.month}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        build_calendar_sheet(writer, cal, args.month, args.year)
        build_person_sheet(writer, pa)
        build_log_sheet(writer, cal, w)
    print(f"Written schedule + logs to {out}")


if __name__ == '__main__':
    main()
