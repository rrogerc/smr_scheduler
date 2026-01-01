import pandas as pd
import json
import argparse
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    # Load data
    try:
        df = pd.read_excel(args.input)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        # Write empty list if file empty/missing
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump([], f)
        return

    # Helper to find col
    def find_col(keywords):
        for col in df.columns:
            norm = "".join(filter(str.isalnum, str(col).lower()))
            if all(k in norm for k in keywords):
                return col
        return None

    first = find_col(['first', 'name'])
    last = find_col(['last', 'name'])
    
    # If explicit columns aren't found, try to guess or use the first columns
    # But usually sync_sheet preserves the headers.
    
    roster = []
    for _, row in df.iterrows():
        fname = str(row[first]).strip() if first else ""
        lname = str(row[last]).strip() if last else ""
        full_name = f"{fname} {lname}".strip()
        if not full_name:
            full_name = "Unknown Name"
            
        roster.append({
            "name": full_name,
        })
    
    # Deduplicate by name just in case
    # (Though sync_sheet dedups by UCID)
    roster.sort(key=lambda x: x['name'])
    
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(roster, f, indent=2)
    
    print(f"✅ Extracted roster for {len(roster)} people to {args.output}")

if __name__ == "__main__":
    main()