#!/usr/bin/env python3
import requests
import pandas as pd
import io
import sys


def fetch_sheet_as_df(sheet_id: str, gid: int = 0) -> pd.DataFrame:
    """
    Fetches the given Google Sheet (must be public) as a pandas DataFrame.
    """
    url = f'https://docs.google.com/spreadsheets/d/{
        sheet_id}/export?format=csv&gid={gid}'
    resp = requests.get(url)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content))


# https://docs.google.com/spreadsheets/d/13awWH0EprYSFEFwALH8BcIi-qB1TFSn6fPgNnlxzESo/edit?gid=1539534942#gid=1539534942
def main():
    # === CONFIGURE THESE ===
    SHEET_ID = '13awWH0EprYSFEFwALH8BcIi-qB1TFSn6fPgNnlxzESo'  # from your URL
    GID = 1539534942  # sheet’s gid (0 is the first tab)
    OUTPUT_FILE = 'availability.xlsx'
    UCID_COL = 'UCID:'
    # =======================

    try:
        df = fetch_sheet_as_df(SHEET_ID, GID)
    except Exception as e:
        print(f"❌ Error fetching sheet: {e}", file=sys.stderr)
        sys.exit(1)

    if UCID_COL not in df.columns:
        print(f"❌ Column '{UCID_COL}' not found in sheet!", file=sys.stderr)
        print("Available columns:", df.columns.tolist(), file=sys.stderr)
        sys.exit(1)

    # If there’s a timestamp column and you want to ensure true chronological order,
    # you can uncomment & adjust the two lines below (replace 'Timestamp' if needed):
    # df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    # df = df.sort_values('Timestamp')

    # Drop older entries, keep only the last (newest) row for each UCID
    df_clean = df.drop_duplicates(subset=[UCID_COL], keep='last')

    # Write out to Excel
    try:
        df_clean.to_excel(OUTPUT_FILE, index=False)
        print(f"✅ Wrote cleaned sheet to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"❌ Error writing Excel file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
