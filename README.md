# Video Processing Scripts

Collection of scripts for processing and organizing video files.

## Setup

### Environment Configuration

Some scripts require environment variables for sensitive information (credentials, paths, etc.).

1. **Copy the example file:**

   ```bash
   cp .env.example .env.local
   ```

2. **Edit `.env.local` with your actual values:**

   ```bash
   # Edit with your NAS credentials, paths, etc.
   vim .env.local
   ```

3. **Never commit `.env.local`** - it's already in `.gitignore`

### Scripts Using Environment Variables

- `backup-to-nas.sh` - Requires NAS credentials in `.env.local`

## Scripts

### Video Timestamp Processing

This is primarily to correct Insta360 exports (prefixed `VID_`), where the raw 360 files have correct timestamps but the exports made at some point later don't.
We can rewrite the timestamps using the original datetime parsed from the filename to ensure these files show up in order in your Final Cut Pro or the like.

- `fix-video-timestamp.sh` - Process single video file timestamps
- `batch-fix-video-timestamps.sh` - Batch process multiple video files  
- `organize-videos-by-date.sh` - Fix timestamps and organize into date folders
- `insta360/offset_filename_datetime.sh` - Correct Insta360 files with wrong date/time

### Backup

- `backup-to-nas.sh` - Backup files to NAS using rsync (requires `.env.local`)
- `backup-local.sh` - Local backup operations
