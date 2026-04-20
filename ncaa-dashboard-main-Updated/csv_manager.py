"""
csv_manager.py
Handles all persistent CSV storage for the NCAA Athlete Dashboard.

Storage layout:
    data/
        <TeamSlug>.csv          e.g. data/Akron_mens_tf.csv
        athlete_<Name>.csv      e.g. data/athlete_Lane_Graham.csv

Oracle-friendly formatting enforced on every save:
    - Dates:         YYYY-MM-DD (ISO 8601 — matches Oracle DATE via TO_DATE)
    - Nulls:         empty string "" replaced with NULL literal for numeric cols,
                     blank string kept for VARCHAR cols (Oracle treats '' as NULL anyway)
    - Strings:       stripped, no embedded newlines, no leading/trailing quotes
    - Numerics:      TIME_SECONDS and MARK_METERS always plain decimals, no units
    - Column names:  UPPER_SNAKE_CASE to match Oracle convention
    - Encoding:      UTF-8

Suggested Oracle SQL*Loader control file snippet is printed by oracle_control_file().
"""

import os
import re
import pandas as pd
import numpy as np

DATA_DIR = "data"

# ── Column definition ─────────────────────────────────────────────────────────
# (python_name, oracle_name, oracle_type, is_numeric)
COLUMN_SPEC = [
    ("Athlete_Name",      "ATHLETE_NAME",      "VARCHAR2(200)",  False),
    ("Athlete_Year",      "ATHLETE_YEAR",       "VARCHAR2(20)",   False),
    ("School",            "SCHOOL",             "VARCHAR2(200)",  False),
    ("Meet_Info",         "MEET_INFO",          "VARCHAR2(500)",  False),
    ("Event",             "EVENT",              "VARCHAR2(100)",  False),
    ("Event_Type",        "EVENT_TYPE",         "VARCHAR2(10)",   False),
    ("Race_Date",         "RACE_DATE",          "DATE",           False),  # YYYY-MM-DD
    ("Mark",              "MARK",               "VARCHAR2(50)",   False),
    ("Time_seconds",      "TIME_SECONDS",       "NUMBER(10,4)",   True),
    ("Mark_meters",       "MARK_METERS",        "NUMBER(10,4)",   True),
    ("Placement_Number",  "PLACEMENT_NUMBER",   "NUMBER(5)",      True),
    ("Round",             "ROUND_DESC",         "VARCHAR2(20)",   False),  # ROUND is reserved in Oracle
]

PYTHON_COLS  = [c[0] for c in COLUMN_SPEC]
ORACLE_COLS  = [c[1] for c in COLUMN_SPEC]
NUMERIC_COLS = {c[0] for c in COLUMN_SPEC if c[3]}
DEDUP_KEYS   = ["Athlete_Name", "Meet_Info", "Event", "Mark", "Placement_Number"]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _team_slug(team_url: str) -> str:
    """
    Derive a safe filename slug from a TFRRS team URL.
    '.../OH_college_m_Akron.html'      → 'Akron_mens_tf'
    '.../TX_college_f_Texas_Tech.html' → 'Texas_Tech_womens_tf'
    """
    basename = re.sub(r"\.html?$", "", team_url.rstrip("/").split("/")[-1])
    parts = basename.split("_")
    gender_map = {"m": "mens", "f": "womens"}
    gender = "mens"
    school_parts = []
    found_college = False
    for p in parts:
        if p.lower() == "college":
            found_college = True
            continue
        if found_college and p.lower() in gender_map:
            gender = gender_map[p.lower()]
            found_college = False
            continue
        if len(p) == 2 and p.isupper() and not school_parts:
            continue  # skip state abbreviation
        school_parts.append(p)
    school = "_".join(school_parts) if school_parts else basename
    return f"{school}_{gender}_tf"


def _athlete_slug(name: str) -> str:
    """'Graham, Lane' → 'Lane_Graham'"""
    name = name.strip()
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    return re.sub(r"\s+", "_", name)


def _oracle_format(df: pd.DataFrame, school: str = "") -> pd.DataFrame:
    """
    Enforce Oracle-friendly formatting on a DataFrame:
      - Ensure all expected columns exist
      - Dates → YYYY-MM-DD strings
      - Numeric cols → plain decimal strings, empty string for NaN
      - String cols → stripped, no newlines, empty string for NaN
      - Column names → UPPER_SNAKE_CASE (Oracle convention)
    """
    df = df.copy()

    # Fill school
    if "School" not in df.columns:
        df["School"] = school
    elif school:
        df["School"] = df["School"].fillna(school)

    # Ensure all python columns exist
    for col in PYTHON_COLS:
        if col not in df.columns:
            df[col] = np.nan

    # Stub Athlete_Name / Athlete_Year if empty
    for col in ("Athlete_Name", "Athlete_Year"):
        if df[col].isna().all():
            df[col] = ""

    # ── Format each column ────────────────────────────────────────────────────
    for col in PYTHON_COLS:
        if col == "Race_Date":
            # Coerce to datetime then format as YYYY-MM-DD; NaT → ""
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
            df[col] = df[col].fillna("")

        elif col in NUMERIC_COLS:
            # Coerce to float, round to 4dp, NaN → ""
            numeric = pd.to_numeric(df[col], errors="coerce")
            df[col] = numeric.apply(
                lambda x: "" if pd.isna(x) else f"{x:.4f}".rstrip("0").rstrip(".")
            )

        else:
            # String: strip whitespace, remove embedded newlines, NaN → ""
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(r"[\r\n]+", " ", regex=True)
                .replace({"nan": "", "None": "", "NaT": ""})
            )

    # Rename to Oracle column names
    rename_map = dict(zip(PYTHON_COLS, ORACLE_COLS))
    df = df[PYTHON_COLS].rename(columns=rename_map)

    return df


def _load_existing(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.DataFrame(columns=ORACLE_COLS)


def _merge_and_save(existing: pd.DataFrame, new_df: pd.DataFrame, path: str) -> pd.DataFrame:
    """Append, deduplicate, sort, and save with Oracle column names."""
    combined = pd.concat([existing, new_df], ignore_index=True)

    # Map dedup keys to Oracle names for comparison
    dedup_oracle = [dict(zip(PYTHON_COLS, ORACLE_COLS))[k]
                    for k in DEDUP_KEYS if k in dict(zip(PYTHON_COLS, ORACLE_COLS))]
    avail_dedup = [c for c in dedup_oracle if c in combined.columns]
    combined[avail_dedup] = combined[avail_dedup].fillna("")
    combined = combined.drop_duplicates(subset=avail_dedup, keep="last")

    sort_cols = [c for c in ["ATHLETE_NAME", "RACE_DATE", "EVENT"] if c in combined.columns]
    combined = combined.sort_values(sort_cols, na_position="last").reset_index(drop=True)
    combined.to_csv(path, index=False, encoding="utf-8")
    return combined


# ── Public API ────────────────────────────────────────────────────────────────

def team_csv_path(team_url: str) -> str:
    _ensure_data_dir()
    return os.path.join(DATA_DIR, f"{_team_slug(team_url)}.csv")


def athlete_csv_path(athlete_name: str) -> str:
    _ensure_data_dir()
    return os.path.join(DATA_DIR, f"athlete_{_athlete_slug(athlete_name)}.csv")


def save_team_data(df: pd.DataFrame, team_url: str, school_name: str = "") -> str:
    path = team_csv_path(team_url)
    existing = _load_existing(path)
    new_df = _oracle_format(df, school=school_name)
    _merge_and_save(existing, new_df, path)
    return path


def save_athlete_data(df: pd.DataFrame, athlete_name: str,
                      team_url: str = "", school_name: str = "") -> str:
    new_df = _oracle_format(df, school=school_name)
    if new_df["ATHLETE_NAME"].eq("").all():
        new_df["ATHLETE_NAME"] = athlete_name

    primary_path = athlete_csv_path(athlete_name)

    if team_url:
        team_path = team_csv_path(team_url)
        _merge_and_save(_load_existing(team_path), new_df, team_path)
        primary_path = team_path

    _merge_and_save(_load_existing(primary_path), new_df, athlete_csv_path(athlete_name))
    return primary_path


def load_team_data(team_url: str) -> pd.DataFrame:
    return _load_existing(team_csv_path(team_url))


def load_athlete_data(athlete_name: str) -> pd.DataFrame:
    return _load_existing(athlete_csv_path(athlete_name))


def list_saved_files() -> list:
    _ensure_data_dir()
    results = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(DATA_DIR, fname)
        try:
            df = pd.read_csv(path, dtype=str)
            results.append({
                "path": path,
                "filename": fname,
                "type": "athlete" if fname.startswith("athlete_") else "team",
                "rows": len(df),
                "athletes": df["ATHLETE_NAME"].nunique() if "ATHLETE_NAME" in df.columns else 0,
                "last_modified": pd.Timestamp(os.path.getmtime(path), unit="s").strftime("%Y-%m-%d %H:%M"),
            })
        except Exception:
            pass
    return results


def oracle_control_file(csv_path: str, table_name: str = "TFRRS_RESULTS") -> str:
    """
    Returns a SQL*Loader control file string for loading a CSV produced by this module.
    Usage:
        print(oracle_control_file("data/Akron_mens_tf.csv", "TFRRS_RESULTS"))
        # Save the output as tfrrs.ctl and run:
        # sqlldr userid=user/pass@db control=tfrrs.ctl log=tfrrs.log
    """
    col_lines = []
    for py_col, ora_col, ora_type, _ in COLUMN_SPEC:
        if ora_type == "DATE":
            col_lines.append(f'    {ora_col} DATE "YYYY-MM-DD"')
        elif ora_type.startswith("NUMBER"):
            col_lines.append(f'    {ora_col}')
        else:
            col_lines.append(f'    {ora_col} CHAR(500)')

    cols_block = ",\n".join(col_lines)

    return f"""-- SQL*Loader control file for {csv_path}
-- Run with: sqlldr userid=<user>/<pass>@<db> control=tfrrs.ctl log=tfrrs.log bad=tfrrs.bad
LOAD DATA
INFILE '{csv_path}'
APPEND INTO TABLE {table_name}
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
{cols_block}
)
"""
