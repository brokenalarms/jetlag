#!/bin/bash
# Library - File operations for organizing and date extraction
# Not executable directly - source this file from other scripts

# Helper: extract YYYY-MM-DD from various filename patterns
derive_date_from_filename() {
  local base="$1"
  
  # Pattern 1: VID_YYYYMMDD_HHMMSS (Insta360)
  if [[ "$base" =~ VID_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 2: IMG_YYYYMMDD_HHMMSS (Insta360/phones)
  if [[ "$base" =~ IMG_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 3: LRV_YYYYMMDD_HHMMSS (Insta360 Low res video)
  if [[ "$base" =~ LRV_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 4: DJI_YYYYMMDDHHMMSS_* (DJI Mavic 3 and newer)
  if [[ "$base" =~ DJI_([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{6})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 5: DSC_YYYYMMDD_HHMMSS (Sony cameras)
  if [[ "$base" =~ DSC_([0-9]{4})([0-9]{2})([0-9]{2})_ ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 6: Screenshot YYYY-MM-DD at HH.MM.SS (macOS screenshots)
  if [[ "$base" =~ Screenshot[[:space:]]([0-9]{4})-([0-9]{2})-([0-9]{2})[[:space:]]at ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 7: Photo YYYY-MM-DD (various formats)
  if [[ "$base" =~ Photo[[:space:]]([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
    echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    return 0
  fi
  
  # Pattern 8: YYYY-MM-DD in filename
  if [[ "$base" =~ ([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local day="${BASH_REMATCH[3]}"
    # Basic validation
    if [[ $year -ge 2000 && $year -le 2099 && $month -ge 1 && $month -le 12 && $day -ge 1 && $day -le 31 ]]; then
      echo "${year}-${month}-${day}"
      return 0
    fi
  fi
  
  # Pattern 9: Generic YYYYMMDD anywhere in filename
  if [[ "$base" =~ ([0-9]{4})([0-9]{2})([0-9]{2}) ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local day="${BASH_REMATCH[3]}"
    # Basic validation: year should be 2000-2099, month 01-12, day 01-31
    # Use 10# prefix to force base-10 interpretation (avoid octal issues with 08, 09)
    if [[ 10#$year -ge 2000 && 10#$year -le 2099 && 10#$month -ge 1 && 10#$month -le 12 && 10#$day -ge 1 && 10#$day -le 31 ]]; then
      echo "${year}-${month}-${day}"
      return 0
    fi
  fi
  
  return 1
}

# Extract date from EXIF data using sips (macOS built-in)
extract_metadata_date() {
  local file="$1"
  local ext="${file##*.}"
  ext="${ext,,}" # lowercase
  
  # Only works on macOS
  if [[ "$(uname)" != "Darwin" ]]; then
    return 1
  fi
  
  # Only try for image files that sips can handle
  case "$ext" in
    jpg|jpeg|png|gif|bmp|tiff|tif|heic|heif)
      # Try DateTimeOriginal from EXIF using sips
      local metadata_date=$(sips -g exif:DateTimeOriginal "$file" 2>/dev/null | grep -o '[0-9]\{4\}:[0-9]\{2\}:[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}')
      if [[ -n "$metadata_date" ]]; then
        # Convert EXIF format (YYYY:MM:DD HH:MM:SS) to YYYY-MM-DD
        local date_part="${metadata_date%% *}"  # Remove time portion
        date_part="${date_part//:/-}"           # Replace colons with hyphens
        echo "$date_part"
        return 0
      fi
      
      # Try CreateDate from EXIF using sips
      metadata_date=$(sips -g exif:CreateDate "$file" 2>/dev/null | grep -o '[0-9]\{4\}:[0-9]\{2\}:[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}')
      if [[ -n "$metadata_date" ]]; then
        local date_part="${metadata_date%% *}"
        date_part="${date_part//:/-}"
        echo "$date_part"
        return 0
      fi
      ;;
  esac
  
  return 1
}

# Get date for a file (from filename or metadata or creation time)
# Usage: get_file_date FILE
get_file_date() {
  local file="$1"
  local base="$(basename "$file")"
  local date_folder=""
  
  # First try: extract date from filename
  date_folder=$(derive_date_from_filename "$base")
  
  # Second try: extract from metadata (only for images on macOS)
  if [[ -z "$date_folder" ]]; then
    date_folder=$(extract_metadata_date "$file")
  fi
  
  # Third try: use file's creation time
  if [[ -z "$date_folder" ]]; then
    # On macOS, use stat with -f "%SB" for birth time
    if [[ "$(uname)" == "Darwin" ]]; then
      date_folder=$(stat -f "%SB" -t "%Y-%m-%d" "$file" 2>/dev/null)
    else
      # On Linux, try birth time first, fall back to modification time
      date_folder=$(stat --format="%w" "$file" 2>/dev/null | cut -d' ' -f1)
      if [[ "$date_folder" == "-" || -z "$date_folder" ]]; then
        date_folder=$(stat --format="%y" "$file" 2>/dev/null | cut -d' ' -f1)
      fi
    fi
  fi
  
  # Return the date or empty if we couldn't determine it
  echo "$date_folder"
}