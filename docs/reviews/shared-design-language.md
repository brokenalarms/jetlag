# Reviewer checklist: Shared design language

The Workflow and Profiles screens were rebuilt to share option rows (`OptionGroup`, `OptionRow`), `GyroflowSettingsRows` and `CameraValue`, so the same control looks the same on both.

## After-screenshots

Rendered off-screen from the branch: `WorkflowView` at 760×1500 with a video profile, Gyroflow available and every step on, and `ProfileEditorView` at 760×1100 for a video profile with Gyroflow enabled. The paths shown are temporary directories created for the render. The renders do not cover a live window, popovers, hover, the toolbar and inspector, or any interaction. Compare them against the branch build in the live app:

| Screen | Light | Dark |
| --- | --- | --- |
| Workflow, all steps on | [light](shared-design-language/light-workflow.png) | [dark](shared-design-language/dark-workflow.png) |
| Profiles, video with Gyroflow | [light](shared-design-language/light-profiles.png) | [dark](shared-design-language/dark-profiles.png) |

## Layout, compared against each screenshot

- [ ] Every option label is in one font and colour
- [ ] No option label ends in a colon
- [ ] Controls in one card share a column
- [ ] The Gyroflow rows are identical on Workflow and Profiles
- [ ] The Camera row is identical on Workflow and Profiles

## Behaviour to try in the live app

The Profiles behaviours #260 (jetlag-cps) rebuilt have no test:

- [ ] Browse fills the Source dir and Ready dir fields
- [ ] A cleared directory field saves as unset
- [ ] Save and Cancel appear only with unsaved changes
