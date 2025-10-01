#!/usr/bin/env bash
# photos-spatial-audio-mix.sh
# Shell wrapper for Photos spatial audio mix AppleScript automation
# Usage: ./photos-spatial-audio-mix.sh [options]

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLESCRIPT_FILE="$SCRIPT_DIR/photos-spatial-audio-mix.applescript"

# Default configuration
MIX_TYPE="Cinematic"
INTENSITY=25
DRY_RUN=0
VERBOSE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mix)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --mix requires a value (Standard, Cinematic, Studio, In-Frame)" >&2; exit 1; }
      MIX_TYPE="$1"
      shift ;;
    --intensity)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --intensity requires a percentage value (0-100)" >&2; exit 1; }
      INTENSITY="$1"
      shift ;;
    --dry-run)
      DRY_RUN=1
      shift ;;
    --verbose|-v)
      VERBOSE=1
      shift ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Automates spatial audio mix changes in Photos app for selected videos."
      echo ""
      echo "Prerequisites:"
      echo "  1. Open Photos app"
      echo "  2. Select videos you want to process"
      echo "  3. Run this script"
      echo ""
      echo "Options:"
      echo "  --mix TYPE        Spatial audio mix type (default: Cinematic)"
      echo "                    Options: Standard, Cinematic, Studio, In-Frame"
      echo "  --intensity N     Intensity percentage 0-100 (default: 25)"
      echo "                    Only applies to Cinematic and Studio mixes"
      echo "  --dry-run         Show what would be done without making changes"
      echo "  --verbose, -v     Enable verbose logging"
      echo "  --help, -h        Show this help"
      echo ""
      echo "Supported Mix Types:"
      echo "  Standard   - Original iPhone recording"
      echo "  In-Frame   - Focus audio on what's visible in frame"
      echo "  Studio     - Clean, professional sound"
      echo "  Cinematic  - Immersive, wide soundstage"
      echo ""
      echo "Examples:"
      echo "  $0                                    # Use Cinematic at 25%"
      echo "  $0 --mix Studio --intensity 50       # Use Studio at 50%"
      echo "  $0 --mix In-Frame                    # Use In-Frame (no intensity)"
      echo "  $0 --dry-run                         # Preview without changes"
      echo ""
      echo "Note: This script uses UI automation and may need accessibility permissions."
      exit 0 ;;
    *)
      echo "ERROR: Unknown option $1" >&2
      echo "Use --help for usage information" >&2
      exit 1 ;;
  esac
done

# Validate mix type
case "$MIX_TYPE" in
  Standard|Cinematic|Studio|In-Frame) ;;
  *)
    echo "ERROR: Invalid mix type '$MIX_TYPE'" >&2
    echo "Valid options: Standard, Cinematic, Studio, In-Frame" >&2
    exit 1 ;;
esac

# Validate intensity
if ! [[ "$INTENSITY" =~ ^[0-9]+$ ]] || [[ $INTENSITY -lt 0 ]] || [[ $INTENSITY -gt 100 ]]; then
  echo "ERROR: Intensity must be a number between 0 and 100" >&2
  exit 1
fi

# Check if AppleScript file exists
if [[ ! -f "$APPLESCRIPT_FILE" ]]; then
  echo "ERROR: AppleScript file not found: $APPLESCRIPT_FILE" >&2
  exit 1
fi

# Check if Photos is running
if ! pgrep -q "Photos"; then
  echo "ERROR: Photos app is not running" >&2
  echo "Please open Photos, select videos to process, and try again" >&2
  exit 1
fi

# Display configuration
echo "🎵 PHOTOS SPATIAL AUDIO MIX AUTOMATION"
echo "→ Mix Type:    $MIX_TYPE"
if [[ "$MIX_TYPE" == "Cinematic" ]] || [[ "$MIX_TYPE" == "Studio" ]]; then
  echo "→ Intensity:   ${INTENSITY}%"
fi
echo "→ Mode:        $([[ $DRY_RUN -eq 1 ]] && echo "DRY RUN" || echo "APPLY CHANGES")"
[[ $VERBOSE -eq 1 ]] && echo "→ Verbose:     Enabled"
echo

if [[ $DRY_RUN -eq 1 ]]; then
  echo "🔍 DRY RUN MODE - No changes will be made"
  echo "This would:"
  echo "  1. Process all selected videos in Photos"
  echo "  2. Change spatial audio mix to: $MIX_TYPE"
  if [[ "$MIX_TYPE" == "Cinematic" ]] || [[ "$MIX_TYPE" == "Studio" ]]; then
    echo "  3. Set intensity to: ${INTENSITY}%"
  fi
  echo "  4. Save changes and move to next video"
  echo
  echo "To actually apply changes, run without --dry-run"
  exit 0
fi

# Confirm before proceeding
echo "⚠️  This will modify spatial audio settings for all selected videos in Photos."
echo "Make sure you have selected only the videos you want to change."
echo
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo "🚀 Starting automation..."
echo "Note: Do not interact with your computer while the script is running."
echo

# Create temporary AppleScript with current settings
TEMP_SCRIPT=$(mktemp /tmp/photos-audio-mix.XXXXXX.applescript)

# Modify the AppleScript with current settings
sed "s/property targetMix : \"Cinematic\"/property targetMix : \"$MIX_TYPE\"/" "$APPLESCRIPT_FILE" | \
sed "s/property targetIntensity : 25/property targetIntensity : $INTENSITY/" > "$TEMP_SCRIPT"

# Add verbose logging if requested
if [[ $VERBOSE -eq 1 ]]; then
  echo "→ Verbose mode enabled - check Console.app for detailed logs"
fi

# Execute the AppleScript
echo "📱 Executing spatial audio automation..."
if osascript "$TEMP_SCRIPT"; then
  echo "✅ Automation completed successfully!"
else
  echo "❌ Automation failed. Check that:"
  echo "   - Photos app is open and videos are selected"
  echo "   - Selected videos have spatial audio support"
  echo "   - Accessibility permissions are granted for Terminal/Script Editor"

  # Clean up temp file
  rm -f "$TEMP_SCRIPT"
  exit 1
fi

# Clean up temp file
rm -f "$TEMP_SCRIPT"

echo
echo "📋 Tips for next time:"
echo "  - Process videos in small batches for reliability"
echo "  - Ensure videos have spatial audio before processing"
echo "  - Use Smart Albums to organize videos by audio type"
echo
echo "🎬 Ready for export to Final Cut Pro with consistent audio mix!"