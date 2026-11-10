"""Country → timezone lookup, from the CSV tables in lib/timezones/."""

from __future__ import annotations

import os
from typing import Optional

TIMEZONE_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timezones")


def get_timezone_for_country(input_country: str) -> Optional[str]:
    """The +HH:MM offset for a country code or name, from lib/timezones/*.csv.

    Returns None when the country or its zone cannot be found.
    """
    country_csv = os.path.join(TIMEZONE_DATA_DIR, "country.csv")
    timezone_csv = os.path.join(TIMEZONE_DATA_DIR, "time_zone.csv")

    # Check if CSV files exist
    if not os.path.exists(country_csv) or not os.path.exists(timezone_csv):
        return None

    # Step 1: Resolve input to country code
    country_code = ""
    if len(input_country) == 2:
        # Input is likely a country code
        country_code = input_country.upper()
    else:
        # Input is country name, find the code
        try:
            with open(country_csv, 'r') as f:
                for line in f:
                    if line.strip() and input_country.lower() in line.lower():
                        country_code = line.split(',')[0].strip()
                        break
        except OSError:
            return None

    if not country_code:
        return None

    # Step 2: Find appropriate timezone for country code and date
    try:
        with open(timezone_csv, 'r') as f:
            timezone_line = ""
            for line in f:
                if f",{country_code}," in line:
                    timezone_line = line.strip()

            if not timezone_line:
                return None

            # Step 3: Extract offset. Columns: zone, country, abbreviation,
            # time_start, gmt_offset (seconds), dst flag.
            parts = timezone_line.split(',')
            if len(parts) >= 6:
                offset_seconds = int(parts[4])
                abs_seconds = abs(offset_seconds)
                hours = abs_seconds // 3600
                minutes = (abs_seconds % 3600) // 60
                sign = "-" if offset_seconds < 0 else "+"
                return f"{sign}{hours:02d}:{minutes:02d}"
    except (OSError, ValueError):
        pass

    return None

def get_country_name(input_country: str) -> str:
    """Get full country name for display"""
    country_csv = os.path.join(TIMEZONE_DATA_DIR, "country.csv")

    if len(input_country) == 2:
        try:
            with open(country_csv, 'r') as f:
                for line in f:
                    if line.startswith(input_country.upper() + ","):
                        return line.split(',', 1)[1].strip().strip('"')
        except OSError:
            pass

    return input_country
