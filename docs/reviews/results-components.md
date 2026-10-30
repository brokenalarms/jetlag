# Reviewer checklist: Results components

The Files panel was rebuilt from `ResultsPanel`, `ResultsTable` and `StatusBadge` in `macos/Sources/Components/` with no intended visual or behavioural change.

## Before-screenshots

Taken from commit `38edf11`, the last one before the rebuild, by rendering `InspectorPanel` off-screen at 1100×600 with five files streamed through the pipeline's events: would-change, unchanged and failed rows, and twelve log lines. Rendering the branch the same way gave a pixel-identical image for all eight; they don't cover a live window, hover, selection, menus or Quick Look. The pending badge's spinner isn't in them either, since every row has finished. Compare them against the branch build in the live app:

| State | Light | Dark |
| --- | --- | --- |
| Files, log closed | [light](results-components-before/light-files.png) | [dark](results-components-before/dark-files.png) |
| Files, log open | [light](results-components-before/light-files-log-open.png) | [dark](results-components-before/dark-files-log-open.png) |
| Nothing run yet | [light](results-components-before/light-idle.png) | [dark](results-components-before/dark-idle.png) |
| Starting up | [light](results-components-before/light-starting-up.png) | [dark](results-components-before/dark-starting-up.png) |

- [ ] Files panel with the log closed matches the screenshot
- [ ] Files panel with the log open matches the screenshot
- [ ] Nothing run yet matches the screenshot
- [ ] Starting up matches the screenshot

## Layout, compared against each screenshot

- [ ] Header: icon, title and file count, and the padding around them
- [ ] Log open: the header and table share the height evenly with the log
- [ ] All seven columns in order, with their titles and auto-fitted widths
- [ ] Status badges: icon and colour for would-change, changed, no change and failed
- [ ] Bottom bar: terminal icon and padding, brighter while the log is open

## Behaviour

- [ ] During a run, a pending row spins beside the stage it last completed
- [ ] A source with no matching media shows its message and the source path, which is selectable
- [ ] The terminal button opens and closes the log, and its tooltip says which it will do
- [ ] Closing and reopening the log returns to the line being read
- [ ] Hovering a cell shows its tooltip; truncated filenames and destinations show the full text
- [ ] Click, ⌘-click and ⇧-click select rows
- [ ] Right-click: Show in Finder and Quick Look act on the selected rows
- [ ] Right-click on a conflicting destination also offers Show Existing File at Destination
- [ ] Space opens Quick Look for the selection, and does nothing with no selection
- [ ] Columns grow as rows stream in; dragging a divider holds that width; double-clicking one fits its widest cell
- [ ] A table wider than the panel scrolls sideways, and its scroller doesn't cover the last row
