#!/usr/bin/env python3
import requests
import pandas as pd
import io
import sys
import argparse
import datetime

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def fetch_sheet_as_df(sheet_id: str, gid: int = 0) -> pd.DataFrame:
    """
    Fetches the given Google Sheet (must be public) as a pandas DataFrame.
    Uses XLSX export to automatically read the first sheet, ignoring GID.
    """
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
    resp = requests.get(url)
    resp.raise_for_status()
    # Read the first sheet (index 0) regardless of its name
    return pd.read_excel(io.BytesIO(resp.content), sheet_name=0)

def find_column_by_keywords(df, *keywords):
    """
    Finds the first original column name in the DataFrame that contains all keywords
    in its normalized (lowercase, alphanumeric) version.
    """
    for col in df.columns:
        normalized_col = "".join(filter(str.isalnum, str(col).lower()))
        if all(kw in normalized_col for kw in keywords):
            return col
    return None

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sheet-id', required=True, help="Google Sheet ID to pull")
    p.add_argument('--term',     choices=['Fall', 'Winter'], required=True, help="Term to generate schedule for")
    p.add_argument('--year',     type=int, required=True, help="Year of the term start")
    args = p.parse_args()

    # === CONFIGURATION ===
    GID = 0
    OUTPUT_FILE = 'availability.xlsx'
    # =======================

    try:
        df = fetch_sheet_as_df(args.sheet_id, GID)
    except Exception as e:
        print(f"❌ Error fetching sheet: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Find required columns by searching for keywords in their original names
    ts_col = find_column_by_keywords(df, 'timestamp')
    ucid_col = find_column_by_keywords(df, 'ucid')

    if not ts_col or not ucid_col:
        missing = [col for col, found in [('Timestamp', ts_col), ('UCID', ucid_col)] if not found]
        print(f"❌ Missing required columns: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # 2. Determine the term and define the valid date range for submissions
    term, year = args.term, args.year
    start_date, end_date = None, None

    # Fall Term: Submissions from August 1st to November 30th.
    if term == 'Fall':
        start_date = datetime.date(year, 8, 1)
        end_date = datetime.date(year, 11, 30)
        print(f"INFO: Filtering for Fall term ({year}) submissions: {start_date} to {end_date}")

    # Winter Term: Submissions from December 1st (previous year) to March 31st.
    elif term == 'Winter':
        start_date = datetime.date(year - 1, 12, 1)
        end_date = datetime.date(year, 3, 31)
        print(f"INFO: Filtering for Winter term ({year}) submissions: {start_date} to {end_date}")

    # 3. Convert timestamp column and filter by date range
    # This is done on a copy to avoid SettingWithCopyWarning
    df_filtered = df.copy()
    df_filtered[ts_col] = pd.to_datetime(df[ts_col]).dt.date
    
    if start_date and end_date:
        initial_rows = len(df_filtered)
        df_filtered = df_filtered[(df_filtered[ts_col] >= start_date) & (df_filtered[ts_col] <= end_date)]
        print(f"INFO: Kept {len(df_filtered)} of {initial_rows} rows within the term date range.")

    if df_filtered.empty:
        print("❌ No submissions found in the specified date range. Cannot generate a schedule.")
        sys.exit(1)

    # 4. Drop older entries, keeping only the last (newest) row for each UCID within the term
    df_clean = df_filtered.sort_values(by=ts_col).drop_duplicates(subset=[ucid_col], keep='last')

    # 5. Write the cleaned data to Excel
    try:
        df_clean.to_excel(OUTPUT_FILE, index=False)
        print(f"✅ Wrote {len(df_clean)} cleaned submissions to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"❌ Error writing Excel file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
