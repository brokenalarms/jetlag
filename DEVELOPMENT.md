# Development Principles

## Architecture

### Source of Truth Hierarchy
- **Base scripts are the source of truth** - functionality should be pushed down to the lowest level script possible
- Wrapper scripts should be thin orchestration layers, not duplicate functionality
- Path handling, validation, and core logic belongs in the base scripts (e.g., `organize-by-date.sh`)
- Parent scripts (e.g., `batch-organize-by-date.sh`, `extract-from-photos.sh`) should primarily handle:
  - Argument parsing and validation for their specific use case
  - Finding/preparing source data
  - Calling base scripts with appropriate arguments

### Path Handling
- **Tilde expansion** should happen in every script that accepts paths
- Use `target_dir="${target_dir/#\~/$HOME}"` pattern consistently
- Never assume relative paths - always treat user-provided paths as intended to be absolute
- Base scripts handle the canonical path processing

### Code Reuse
- Avoid duplicating logic between scripts
- If multiple scripts need the same functionality, it belongs in the base script or a shared library
- Wrapper scripts should delegate to base scripts rather than reimplementing

## Examples

### Good: Thin wrapper
```bash
# extract-from-photos.sh
args=("--source" "$source_dir" "--target" "$target_dir" "--template" "$template" "--label" "$label")
exec "$SCRIPT_DIR/batch-organize-by-date.sh" "${args[@]}"
```

### Bad: Duplicated functionality
```bash
# Don't reimplement file finding, organization logic, etc. in wrapper scripts
```

### Path Handling Pattern
```bash
# In every script that accepts paths:
target_dir="${target_dir/#\~/$HOME}"
source_dir="${source_dir/#\~/$HOME}"
```