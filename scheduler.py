# schedule.py
# Generates a monthly schedule calendar and per-person summary from availability responses.
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
#    * If no eligible senior (or insufficient staff), relax weekly cap; if still none, warn.
#    * Respect individual availability per weekday and slot.

TIME_SLOTS = ["9AM-11AM", "11AM-1PM", "1PM-3PM", "3PM-5PM"]


def load_availability(path):
    # Load responses and normalize column names
    df = pd.read_excel(path, sheet_name=0)
    df.columns = df.columns.str.strip()

    people = []
    for _, row in df.iterrows():
        # Normalize name columns
        first = row.get('First Name', row.get('First Name:', ''))
        last = row.get('Last Name', row.get('Last Name:', ''))
        name = f"{first} {last}".strip()
        senior = str(row.get('Are you senior?', '')).strip().lower() == 'yes'
        availability = {}
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            col = f'When is your weekly availability? [{day}]'
            raw = row.get(col, '')
            if pd.isna(raw) or not raw:
                slots = []
            else:
                slots = [s.strip() for s in str(raw).split(',') if s.strip()]
            availability[day] = set(slots)
        people.append({
            'name': name,
            'senior': senior,
            'availability': availability,
            'assignments': {}
        })
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
            weekday = calendar.day_name[date.weekday()]
            calendar_assign.setdefault(date, {})
            for slot in TIME_SLOTS:
                # assign senior
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

                # assign remaining
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

                calendar_assign[date][slot] = [p['name'] for p in assigned]
                for p in assigned:
                    p['assignments'][week_no] += 1
                    person_assignments[p['name']].append((date, slot))

    return calendar_assign, person_assignments, warnings


def build_calendar_sheet(writer, calendar_assign, month, year):
    cal = calendar.Calendar()
    month_name = calendar.month_name[month]
    weeks = cal.monthdays2calendar(year, month)

    # Prepare rows: for each week: 1 date row + 4 slot rows
    rows = []
    for week in weeks:
        # date row (include all month days, including weekends)
        date_row = []
        for day, wd in week:
            if day == 0:
                date_row.append('')
            else:
                date_row.append(str(day))
        rows.append(date_row)

        # slot rows (with time label in each cell, weekends blank)
        for slot in TIME_SLOTS:
            slot_row = []
            for day, wd in week:
                if day == 0 or wd >= 5:
                    slot_row.append('')
                else:
                    dt = datetime.date(year, month, day)
                    names = calendar_assign.get(dt, {}).get(slot, [])
                    slot_row.append(f"{slot}: {', '.join(names)}")
            rows.append(slot_row)

    df = pd.DataFrame(
        rows, columns=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
    ws = writer.book.add_worksheet('Monthly Schedule')
    writer.sheets['Monthly Schedule'] = ws

    # Title and headers
    ws.merge_range(0, 0, 0, 6, f"{month_name} {year}")
    for col, dow in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']):
        ws.write(1, col, dow)

    # Write rows starting at row 2
    for r, row in enumerate(rows, start=2):
        for c, val in enumerate(row):
            ws.write(r, c, val)

    # Format
    ws.set_default_row(30)
    for col in range(7):
        ws.set_column(col, col, 20)


def build_person_sheet(writer, person_assignments):
    rows = []
    for name, assigns in person_assignments.items():
        rows.append({
            'Name': name,
            'Total Shifts': len(assigns),
            'Assignments': "; ".join(f"{d.strftime('%Y-%m-%d')} {s}" for d, s in assigns)
        })
    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name='Person Schedule', index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='Path to availability Excel')
    parser.add_argument('--month', type=int, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--output', default=None,
                        help='Output schedule Excel path')
    args = parser.parse_args()

    people = load_availability(args.input)
    cal_assign, person_assignments, warnings = assign_slots(
        people, args.month, args.year)

    # console output
    print("=== Assignment Summary ===")
    for date, slots in sorted(cal_assign.items()):
        print(date)
        for slot, names in slots.items():
            print(f"  {slot}: {', '.join(names)}")
    print("\n=== Warnings ===")
    for w in warnings:
        print(w)
    print("\n=== Per-Person Assignments ===")
    for name, assigns in person_assignments.items():
        print(f"{name} ({len(assigns)}): {
              ', '.join(f'{d} {s}' for d, s in assigns)}")

    # write Excel file
    out = args.output or f"schedule_{args.month}_{args.year}.xlsx"
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        build_calendar_sheet(writer, cal_assign, args.month, args.year)
        build_person_sheet(writer, person_assignments)
    print(f"Written schedule to {out}")


if __name__ == '__main__':
    main()
