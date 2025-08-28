# Video Processing Scripts - Business Logic Requirements

## Core Principles

1. **Never run with --apply or --verbose unless explicitly instructed by user**
2. **Timezone-aware metadata takes priority over UTC metadata**
3. **DST handling must be date-aware for manual timezone specification**
4. **Template processing must validate required parameters and fail fast**
5. **Path construction must handle trailing/leading slashes intelligently**
6. **Separate data from presentation**: Pass raw data between functions, format only for display
7. **exiftool** should be called once for get and once for set, caching data and then building back with variables - no multiple calls

## fix-video-timestamp.sh Business Logic

### Input Processing
- Single video file argument required
- Location OR timezone argument (not both)
- --apply flag for actual changes (default: dry run)

### Timestamp Detection Priority Order
1. Keys:CreationDate (timezone-aware, e.g., "2025-05-26 12:04:08+02:00")
2. DateTimeOriginal 
3. MediaCreateDate (typically UTC)
4. File modification time (fallback)

### Timezone Handling
- **Manual timezone (--timezone +0200)**: Apply directly to UTC metadata
- **Location code (--location DE)**: 
  - Look up timezone for country/location
  - Apply DST rules based on video date
  - Germany: CET (+0100) Nov-Mar, CEST (+0200) Mar-Oct
- **Keys:CreationDate present**: Extract timezone from metadata, no conversion needed

### Change Detection
- Compare file timestamp against corrected timestamp
- Only show change if timestamps differ
- Display source of timezone (location, manual, or metadata)

### Expected Output Formats
```
Video: IMG_1897.MOV
  Current: 2025-05-26 10:04:08 (UTC from MediaCreateDate)
  Corrected: 2025-05-26 12:04:08+02:00 (DE → CEST)
  📅 Would change file timestamp
```

## batch-fix-video-timestamp.sh Business Logic

### Input Processing
- Directory of video files
- Same timezone/location options as single file version
- Process all .mp4, .mov, .insv, .lrv files

### Processing Rules
- Skip files that don't need changes
- Continue on individual file errors
- Report summary of processed/failed files
- Set BATCH_MODE=1 to suppress individual completion messages

## organize-by-date.sh Business Logic

### Input Processing
- Single file argument required
- --target directory required
- --template (default: "{{YYYY-MM-DD}}")
- --label required if template contains {{label}}

### Template Processing
- Validate template requirements before processing
- Fail fast if required parameters missing
- Support variables: {{YYYY}}, {{MM}}, {{DD}}, {{YYYY-MM-DD}}, {{label}}
- Example: "{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/" → "2025/Germany/2025-05-26/"

### Path Construction
- Handle trailing/leading slashes: `${target_dir%/}/${organized_path#/}`
- Avoid double slashes in final paths
- Create directories as needed in --apply mode

### File Handling Rules
1. **Already organized**: Skip if file already in correct location
2. **Duplicate exists with same size**: Remove source file
3. **Duplicate exists with different size**: Error and skip
4. **No duplicate**: Move file to organized location

## batch-organize-by-date.sh Business Logic

### Input Processing
- Directory of files to organize
- Same options as single file version
- Process all files in directory

### Processing Rules
- Use single file script for each file
- Continue on individual errors
- Report summary statistics

## media-pipeline.sh Business Logic

### Pipeline Steps
1. **Fix video timestamps** using fix-video-timestamp.sh
2. **Organize by date** using organize-by-date.sh

### Input Requirements
- --source directory (or MEDIA_PIPELINE_SOURCE env var)
- --target directory (or MEDIA_PIPELINE_TARGET env var) 
- --label required (for template substitution)
- Location/timezone for timestamp fixing

### Template Handling
- Use MEDIA_PIPELINE_TEMPLATE from env (default: "{{YYYY-MM-DD}}")
- Pass template and label separately to organize-by-date.sh
- Avoid bash parameter expansion with templates containing braces

### Error Handling
- Set BATCH_MODE=1 for timestamp fixing
- Stop processing file if timestamp fix fails
- Continue with other files if organization fails
- Report final statistics

### Environment Variables
```bash
MEDIA_PIPELINE_SOURCE="Raw/"
MEDIA_PIPELINE_TARGET="Ready/"  
MEDIA_PIPELINE_TEMPLATE="{{YYYY}}/{{label}}/{{YYYY}}-{{MM}}-{{DD}}/"
```

## Test Cases to Validate

### Timezone Handling
- iPhone video with Keys:CreationDate → Use timezone from metadata
- iPhone video with only MediaCreateDate + --location DE → Apply CEST in May
- GoPro video + --timezone +0700 → Apply manual offset

### Template Processing  
- Template with {{label}} but no --label provided → Fail with error
- Template "{{YYYY}}/{{label}}/{{DD}}" with --label "Germany" → "2025/Germany/26"
- Empty template → Use default "{{YYYY-MM-DD}}"

### Path Construction
- target_dir="Ready/" + organized_path="2025/Germany/26" → "Ready/2025/Germany/26"
- target_dir="Ready" + organized_path="2025/Germany/26" → "Ready/2025/Germany/26"  
- target_dir="Ready/" + organized_path="/2025/Germany/26" → "Ready/2025/Germany/26"

### File Operations
- File already in correct location → Skip with "Already organized"
- Duplicate with same size → Remove source
- Duplicate with different size → Error, skip file
- No duplicate → Move to organized location

## Data vs Presentation Architecture

### Data Layer (Internal Functions)
- Functions return raw timestamps: "2025-05-26 12:04:08+02:00"
- Pass epoch seconds, ISO dates, or structured data
- No formatting, colors, or display elements
- Example: `get_best_timestamp()` returns raw timestamp string

### Presentation Layer (User Output)
- Format data only at display time
- Add colors, emojis, alignment only for user output
- Never parse formatted strings back to data
- Example: Display "Current: 2025-05-26 10:04:08 (UTC from MediaCreateDate)"

### Anti-Pattern: String Parsing
```bash
# WRONG: Parsing formatted output
formatted=$(some_function --pretty)
parsed=$(echo "$formatted" | sed 's/.*: //')

# CORRECT: Separate data and presentation
raw_data=$(get_raw_data)
display_formatted_data "$raw_data"
```

## Regression Prevention

### Critical Bugs to Avoid
1. **Template corruption**: Bash parameter expansion with braces in default values
2. **Change detection errors**: Comparing metadata fields instead of file vs corrected timestamps
3. **Double slash paths**: From trailing slash + leading slash concatenation
4. **UTC vs local confusion**: Using MediaCreateDate when Keys:CreationDate available
5. **DST errors**: Using CET in summer instead of CEST for Germany
6. **String parsing**: Extracting data from formatted output with sed/regex

### Validation Points
- Always test with iPhone videos from Google Photos (have Keys:CreationDate)
- Test with files in May/June for DST validation
- Test template processing with missing/present label parameter
- Test path construction with various trailing slash combinations
- Verify dry run shows correct "Would move to" paths without double slashes
- Ensure functions return raw data, not formatted strings