# JSONL + schema for app ↔ pipeline IPC

## Problem

The macOS app communicates with `media-pipeline.py` via ad-hoc `@@key=value` lines on stdout. This format has no schema, no nesting, no type information, and no way to represent lists or optional fields cleanly. Every new field requires updating the print site, the Swift parser (`parseMachineReadableLine()`), and any intermediate Python code that forwards the values.

This is the final step in the pipeline migration chain:
1. Pyrefly type checking — enforces type safety across Python scripts (done)
2. Typed return contracts — functions return dataclasses instead of printing `@@` (spec exists)
3. Subprocess → module calls — callers receive typed objects directly (spec exists)
4. **JSONL + schema for app IPC** (this spec) — structured output at the process boundary

## Prerequisite

**Subprocess → module calls** must be complete first. Once internal calls are typed, the only remaining `@@` usage is the top-level pipeline → macOS app boundary. This spec replaces that boundary protocol.

## Design

### Output format

Each pipeline event is a single JSON object on one line (JSONL):

```json
{"event":"pipeline_file","file":"test.mp4"}
{"event":"stage_complete","stage":"ingest"}
{"event":"tag_result","file":"test.mp4","action":"tagged","tags_added":["GoPro","Japan"],"exif_make":"GoPro","exif_model":"HERO12 Black"}
{"event":"stage_complete","stage":"tag"}
{"event":"timestamp_result","file":"test.mp4","action":"fixed","original_time":"2025:06:18 07:25:21","corrected_time":"2025:06:18 07:25:21+09:00","source":"DateTimeOriginal","timezone":"+09:00"}
{"event":"stage_complete","stage":"fix-timestamp"}
{"event":"organize_result","file":"test.mp4","action":"copied","dest":"/path/to/2025/2025-06-18/test.mp4"}
{"event":"stage_complete","stage":"output"}
{"event":"pipeline_result","file":"test.mp4","result":"changed"}
```

### Schema

Define in a new file `scripts/pipeline-schema.yaml` (or as Python dataclasses that generate the schema). Each event type has a fixed set of fields with types:

```yaml
events:
  pipeline_file:
    file: string
  stage_complete:
    stage: string  # ingest | tag | fix-timestamp | output | gyroflow | archive-source
  tag_result:
    file: string
    action: string  # tagged | already_correct
    tags_added: list[string]
    exif_make: string
    exif_model: string
  timestamp_result:
    file: string
    action: string  # fixed | would_fix | no_change | error | tz_mismatch
    original_time: string
    corrected_time: string
    source: string
    timezone: string
  organize_result:
    file: string
    action: string  # copied | moved | skipped | overwrote | would_copy | would_move
    dest: string
  gyroflow_result:
    file: string
    action: string  # generated | skipped | would_generate
    gyroflow_path: string
    error: string
  pipeline_result:
    file: string
    result: string  # changed | would_change | unchanged | failed
```

### Emission

Replace the current `emit()` function in media-pipeline.py:

```python
# Current:
def emit(key, value):
    if _machine_output:
        print(f"@@{key}={value}", flush=True)

# New:
def emit_event(event_type: str, **fields):
    if _machine_output:
        print(json.dumps({"event": event_type, **fields}), flush=True)
```

The dataclasses from the typed-return-contracts spec feed directly into `emit_event()`:

```python
result: TagResult = _tag_mod.tag_media_file(...)
emit_event("tag_result",
    file=result.file,
    action=result.action,
    tags_added=result.tags_added,
    exif_make=result.exif_make,
    exif_model=result.exif_model,
)
```

### Swift app parser

Replace regex-based `parseMachineReadableLine()` with:

```swift
func parsePipelineEvent(_ line: String) -> PipelineEvent? {
    guard let data = line.data(using: .utf8),
          let json = try? JSONDecoder().decode(PipelineEvent.self, from: data)
    else { return nil }
    return json
}
```

`PipelineEvent` is a Swift enum with associated values matching the schema. The schema file can be used to generate the Swift types, or they can be maintained manually (small surface area).

### Backward compatibility

Transition period: support both formats via `--output-format`:

```
media-pipeline.py --output-format jsonl ...   # new format
media-pipeline.py ...                          # default: @@key=value (legacy)
```

The macOS app switches to `--output-format jsonl` immediately. CLI users see no change. After one release cycle, `@@` becomes deprecated and eventually removed.

### Extension for time-correction spec

The time-correction spec defines new keys (`correction_mode`, `time_offset_seconds`, `time_offset_display`, `renamed_to`). These become fields on existing event types:

```json
{"event":"timestamp_result","file":"test.mp4","action":"fixed","correction_mode":"time","time_offset_seconds":3600,"time_offset_display":"+1h 0m 0s",...}
{"event":"rename_result","file":"test.mp4","original":"VID_20250505_130334.mp4","renamed_to":"VID_20250506_140334.mp4"}
```

## Implementation order

1. Define schema file (`scripts/pipeline-schema.yaml`)
2. Add `emit_event()` to media-pipeline.py alongside existing `emit()`
3. Add `--output-format` flag (default: `@@`, option: `jsonl`)
4. Wire `emit_event()` calls in `process_file()` for JSONL mode
5. Update Swift `parseMachineReadableLine()` to handle both formats
6. Switch app to `--output-format jsonl`
7. Deprecate `@@` format

## Files to modify

- `scripts/media-pipeline.py` — `emit_event()`, `--output-format` flag
- `scripts/pipeline-schema.yaml` — new schema definition
- `macos/` — Swift pipeline event parser

## Verification

- Existing tests pass (default format unchanged)
- New test: pipeline with `--output-format jsonl` produces valid JSON on each line
- Swift tests: parse JSONL events correctly
- Manual: run pipeline with both formats, compare results

## Relationship to other specs

- **Depends on**: subprocess-to-module-calls.md (typed returns must exist for clean emission)
- **Enables**: time-correction-pipeline-step.md (new fields ship as JSONL from day one)
