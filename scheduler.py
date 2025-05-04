#!/usr/bin/env python3
"""
schedule.py

Usage:
    python schedule.py responses.xlsx 2025 05
    # or interactively, omit year/month to be prompted
"""

import sys
import argparse
import pandas as pd
import calendar
from datetime import date

TIME_SLOTS = ["9AM-11AM", "11AM-1PM", "1PM-3PM", "3PM-5PM"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def load_people(responses_file):
    df = pd.read_excel(responses_file)
    people = []
    for _, row in df.iterrows():
        person = {
            "name": f"{row['First Name: '].strip()} {row['Last Name:'].strip()}",
            "senior": str(row["Are you senior?"]).strip().lower().startswith("y"),
            "avail": {
                wd: row[f"When is your weekly availability? [{wd}]"].strip()
                for wd in WEEKDAYS
            }
        }
        people.append(person)
    return people


def month_weeks(year, month):
    """
    Return a list of weeks; each week is a list of date objects for Mon-Fri,
    with only those dates in the requested month.
    """
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        # filter Mon–Fri and only keep dates in this month
        wk = [d for d in week if d.month == month and d.weekday() < 5]
        if wk:
            weeks.append(wk)
    return weeks


def build_schedule(people, year, month):
    # Prepare lookup by weekday & slot
    schedule_rows = []
    weeks = month_weeks(year, month)

    for week_idx, week in enumerate(weeks, start=1):
        # track per-person counts in this week
        weekly_count = {p['name']: 0 for p in people}

        for day in week:
            wd = calendar.day_name[day.weekday()]
            for slot in TIME_SLOTS:
                # eligible people who listed this slot on this weekday
                elig = [p for p in people if p['avail'][wd] == slot]
                if len(elig) < 3 or not any(p['senior'] for p in elig):
                    raise RuntimeError(
                        f"Not enough available (and at least one senior) for {
                            wd} {slot}"
                    )
                # choose one senior first
                seniors = [p for p in elig if p['senior']]
                # sort candidates by how many shifts they've had this week
                seniors.sort(key=lambda p: weekly_count[p['name']])
                chosen = []
                chosen.append(seniors[0])
                # now fill remaining two spots from all eligibles, excluding that senior
                rest = [p for p in elig if p['name'] != seniors[0]['name']]
                rest.sort(key=lambda p: weekly_count[p['name']])
                chosen += rest[:2]

                # record assignment and bump counts
                for p in chosen:
                    weekly_count[p['name']] += 1

                # add to final schedule table
                schedule_rows.append({
                    "Date": day.isoformat(),
                    "Day": wd,
                    "Time Slot": slot,
                    "Person 1": chosen[0]['name'],
                    "Person 2": chosen[1]['name'],
                    "Person 3": chosen[2]['name']
                })

    return pd.DataFrame(schedule_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("responses", help="path to form responses .xlsx")
    parser.add_argument("year", nargs="?", type=int, help="e.g. 2025")
    parser.add_argument("month", nargs="?", type=int, help="1–12")
    args = parser.parse_args()

    if not args.year or not args.month:
        args.year = int(input("Year (YYYY): ").strip())
        args.month = int(input("Month (1–12): ").strip())

    people = load_people(args.responses)
    df_schedule = build_schedule(people, args.year, args.month)

    out_name = f"{args.year:04d}_{args.month:02d}_schedule.xlsx"
    df_schedule.to_excel(out_name, index=False)
    print(f"Schedule written to {out_name}")


if __name__ == "__main__":
    main()
