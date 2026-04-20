import pandas as pd
import re

# Detects whether a mark is a track (time) or field (distance) event
def detect_mark_type(mark):
    if pd.isna(mark) or mark in ('NT', 'NM', 'FOUL', 'DNS', 'DNF', 'DQ'):
        return 'invalid'
    mark = str(mark).strip()
    # Field event: ends in 'm', or is a plain decimal distance like '43.41'
    # that came from a field event column (we check context in classify_event)
    if re.match(r'^\d+\.\d+m$', mark):
        return 'field'
    # Track event: mm:ss.ss or ss.ss
    if re.match(r'^\d{1,2}:\d{2}\.\d+$', mark) or re.match(r'^\d{1,2}\.\d+$', mark):
        return 'track'
    return 'invalid'

# Converts a track time string to total seconds (e.g. "4:03.45" → 243.45)
def convert_time_to_seconds(mark):
    if pd.isna(mark) or str(mark).strip() in ('NT', 'NM', 'FOUL', 'DNS', 'DNF', 'DQ'):
        return None
    mark = str(mark).strip()
    try:
        if ':' in mark:
            minutes, seconds = mark.split(':')
            return int(minutes) * 60 + float(seconds)
        else:
            return float(mark)
    except:
        return None

# Extracts numeric meters from a field event mark (e.g. "17.29m" → 17.29, "43.41" → 43.41)
def convert_field_mark_to_meters(mark):
    if pd.isna(mark) or str(mark).strip() in ('NT', 'NM', 'FOUL', 'DNS', 'DNF', 'DQ'):
        return None
    mark = str(mark).strip()
    try:
        # Strip trailing 'm' if present
        return float(mark.rstrip('m'))
    except:
        return None

# Known field event abbreviations on TFRRS
FIELD_EVENTS = {
    'SP', 'DT', 'HT', 'WT', 'JT',           # throws
    'LJ', 'TJ', 'HJ', 'PV',                  # jumps
    'Shot Put', 'Discus', 'Hammer', 'Weight Throw', 'Javelin',
    'Long Jump', 'Triple Jump', 'High Jump', 'Pole Vault',
    # indoor/outdoor variants
    'Shot Put (Indoor)', 'Shot Put (Outdoor)',
    'Discus (Outdoor)', 'Hammer (Outdoor)', 'Weight Throw (Indoor)',
}

def is_field_event(event):
    if pd.isna(event):
        return False
    event_str = str(event).strip()
    # Direct match
    if event_str in FIELD_EVENTS:
        return True
    # Partial match for verbose names
    field_keywords = ['shot', 'discus', 'hammer', 'weight', 'javelin',
                      'jump', 'vault']
    return any(kw in event_str.lower() for kw in field_keywords)

# Extracts date from the Meet_Info column
def extract_date_from_meet_info(meet_info):
    try:
        match = re.search(r'([A-Za-z]{3,9}\s\d{1,2}(?:-\s?\d{1,2})?,?\s\d{4})', meet_info)
        if match:
            date_str = match.group(1)
            # Handle date ranges like 'Apr 17-18, 2025' → pick the first day
            date_str = date_str.replace('-', ' ').split()[0:2] + [date_str.split()[-1]]
            date_cleaned = ' '.join(date_str)
            return pd.to_datetime(date_cleaned, errors='coerce')
        else:
            return pd.NaT
    except:
        return pd.NaT

# Extracts the numeric placement from Place column
# Handles: "3rd (F)", "1st (F)", "11th (P)", "27th (P)", "5th", plain integers
def extract_placement(place):
    match = re.match(r'(\d+)', str(place))
    if match:
        return int(match.group(1))
    return None

# Extracts the round indicator from Place column: "F" = Final, "P" = Prelim
def extract_round(place):
    match = re.search(r'\(([FP])\)', str(place))
    if match:
        return 'Final' if match.group(1) == 'F' else 'Prelim'
    return None

# Cleans the scraped TFRRS DataFrame, handling both track and field events
def clean_tfrrs_data(df):
    df = df.copy()

    df['Race_Date'] = df['Meet_Info'].apply(extract_date_from_meet_info)
    df['Placement_Number'] = df['Place'].apply(extract_placement)
    df['Round'] = df['Place'].apply(extract_round)

    # Determine event type per row
    df['Event_Type'] = df['Event'].apply(lambda e: 'Field' if is_field_event(e) else 'Track')

    # For track events: convert mark to seconds
    df['Time_seconds'] = df.apply(
        lambda row: convert_time_to_seconds(row['Mark']) if row['Event_Type'] == 'Track' else None,
        axis=1
    )

    # For field events: convert mark to meters
    df['Mark_meters'] = df.apply(
        lambda row: convert_field_mark_to_meters(row['Mark']) if row['Event_Type'] == 'Field' else None,
        axis=1
    )

    return df
