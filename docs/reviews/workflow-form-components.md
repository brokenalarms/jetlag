# Reviewer checklist: Workflow form components

The Workflow screen was rebuilt from `macos/Sources/Components/` with no intended visual or behavioural change.

## Before-screenshots

Taken from commit `ef3202d`, the last one before the rebuild, by rendering `WorkflowView` off-screen with a video profile and Gyroflow available. The profile name is not in a loaded profiles file, so the picker renders blank. Rendering the branch the same way gave a pixel-identical image for all six; they don't cover a live window, the file panel, popovers or hover. Compare them against the branch build in the live app:

| State | Light | Dark |
| --- | --- | --- |
| All optional steps on | [light](workflow-form-components-before/light-all-steps-on.png) | [dark](workflow-form-components-before/dark-all-steps-on.png) |
| All optional steps off | [light](workflow-form-components-before/light-optional-steps-off.png) | [dark](workflow-form-components-before/dark-optional-steps-off.png) |
| Run in progress | [light](workflow-form-components-before/light-running.png) | [dark](workflow-form-components-before/dark-running.png) |

- [ ] All optional steps on matches the screenshot
- [ ] All optional steps off matches the screenshot
- [ ] A run in progress matches the screenshot

## Layout, compared against each screenshot

- [ ] Profile selector: label, picker and the vertical padding above and below them
- [ ] Profile load error: message, detail, file path and Reveal in Finder
- [ ] Chip bar: chip tint, icon and label, chevrons between chips, rule and shadow beneath
- [ ] Chip bar collapses to icons when narrow; hovering a chip names it; labels never wrap
- [ ] Card header: icon, title, help button, then Required or the check circle
- [ ] Required card: fainter header tint and border than an active optional card
- [ ] Inactive card: secondary-coloured icon and title, grey border, no body
- [ ] Card body: divider and inner padding on all six steps
- [ ] Tag rows: Tags and Camera labels right-aligned in one column
- [ ] Number fields (time offset, max zoom, zoom window) keep their widths
- [ ] Execution bar: bar material, padding, segmented picker, Run, and Cancel while running

## Behaviour

- [ ] Clicking an optional card's header toggles it, and its chip appears or disappears
- [ ] A required card's header does nothing when clicked
- [ ] The help button opens its popover without toggling the card
- [ ] Source: submitting, leaving the field, and Browse each re-read the source (the timestamp source row updates)
- [ ] Ready and archive folders: Browse fills the field; a long path truncates at the head, with the full path in the tooltip
- [ ] An invalid directory or timezone shows its error under the field and disables Run
- [ ] Companion files and update-filename-dates toggles are disabled when they don't apply
- [ ] The controls are disabled during a run; ⌘↩ runs; Cancel stops the run
