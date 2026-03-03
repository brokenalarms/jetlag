import Foundation

enum Strings {

    // MARK: - Common

    enum Common {
        static let cancel = String(localized: "common.cancel", defaultValue: "Cancel")
        static let delete = String(localized: "common.delete", defaultValue: "Delete")
        static let browse = String(localized: "common.browse", defaultValue: "Browse...")
        static let done = String(localized: "common.done", defaultValue: "Done")
        static let revealInFinder = String(localized: "common.revealInFinder", defaultValue: "Reveal in Finder")
    }

    // MARK: - Navigation

    enum Nav {
        static let workflow = String(localized: "nav.workflow", defaultValue: "Workflow")
        static let profiles = String(localized: "nav.profiles", defaultValue: "Profiles")
        static let mediaProfiles = String(localized: "nav.mediaProfiles", defaultValue: "Media Profiles")
    }

    // MARK: - Pipeline steps

    enum Pipeline {
        static let ingestLabel = String(localized: "pipeline.ingest.label", defaultValue: "Ingest")
        static let tagLabel = String(localized: "pipeline.tag.label", defaultValue: "Tag")
        static let fixTimestampsLabel = String(localized: "pipeline.fixTimestamps.label", defaultValue: "Fix Timestamps")
        static let organizeLabel = String(localized: "pipeline.organize.label", defaultValue: "Organize")
        static let gyroflowLabel = String(localized: "pipeline.gyroflow.label", defaultValue: "Gyroflow")
        static let archiveSourceLabel = String(localized: "pipeline.archiveSource.label", defaultValue: "Archive Source")

        static let ingestHelp = String(localized: "pipeline.ingest.help",
            defaultValue: "Copy files from source to working directory for processing")
        static let tagHelp = String(localized: "pipeline.tag.help",
            defaultValue: "Apply Finder tags and EXIF metadata from profile")
        static let fixTimestampsHelp = String(localized: "pipeline.fixTimestamps.help",
            defaultValue: "Correct timezone labelling and/or camera clock errors")
        static let organizeHelp = String(localized: "pipeline.organize.help",
            defaultValue: "Move processed files into date-based folders in ready directory")
        static let gyroflowHelp = String(localized: "pipeline.gyroflow.help",
            defaultValue: "Generate Gyroflow stabilization project files (requires gyro data)")
        static let archiveSourceHelp = String(localized: "pipeline.archiveSource.help",
            defaultValue: "Act on source folder after processing (archive or delete)")
    }

    // MARK: - Workflow

    enum Workflow {
        static let profileLabel = String(localized: "workflow.profile.label", defaultValue: "Profile")
        static let modeLabel = String(localized: "workflow.mode.label", defaultValue: "Mode")
        static let tagsLabel = String(localized: "workflow.tags.label", defaultValue: "Tags:")
        static let cameraLabel = String(localized: "workflow.camera.label", defaultValue: "Camera:")
        static let groupLabel = String(localized: "workflow.group.label", defaultValue: "Group")
        static let sourceActionLabel = String(localized: "workflow.sourceAction.label", defaultValue: "Source action:")

        static let sourceDirPlaceholder = String(localized: "workflow.sourceDir.placeholder", defaultValue: "SD card or directory path")
        static let readyDirPlaceholder = String(localized: "workflow.readyDir.placeholder", defaultValue: "Ready directory path")
        static let tagPlaceholder = String(localized: "workflow.tag.placeholder", defaultValue: "tag1, tag2")
        static let makePlaceholder = String(localized: "workflow.make.placeholder", defaultValue: "Make")
        static let modelPlaceholder = String(localized: "workflow.model.placeholder", defaultValue: "Model")
        static let groupPlaceholder = String(localized: "workflow.group.placeholder", defaultValue: "Optional")
        static let timezonePlaceholder = String(localized: "workflow.timezone.placeholder", defaultValue: "+HHMM")
        static let selectProfile = String(localized: "workflow.selectProfile", defaultValue: "Select...")
        static let selectTimezone = String(localized: "workflow.selectTimezone", defaultValue: "Select timezone...")
        static let searchTimezones = String(localized: "workflow.searchTimezones", defaultValue: "Search timezones...")

        static let copyCompanionToggle = String(localized: "workflow.copyCompanion.toggle", defaultValue: "Copy companion files")
        static let noCompanionFiles = String(localized: "workflow.noCompanionFiles", defaultValue: "No companion files noted for this device")
        static let appendTimezoneToggle = String(localized: "workflow.appendTimezone.toggle", defaultValue: "Append timezone to group folder")
        static let readyDirRequired = String(localized: "workflow.readyDirRequired", defaultValue: "Set ready directory above")

        static let archiveOption = String(localized: "workflow.archive.option", defaultValue: "Archive")
        static let deleteOption = String(localized: "workflow.delete.option", defaultValue: "Delete")
        static let dryRunOption = String(localized: "workflow.dryRun.option", defaultValue: "Dry Run")
        static let applyOption = String(localized: "workflow.apply.option", defaultValue: "Apply")

        static let runButton = String(localized: "workflow.run.button", defaultValue: "Run")
        static let runningButton = String(localized: "workflow.running.button", defaultValue: "Running...")

        static let typeManuallyHelp = String(localized: "workflow.typeManually.help", defaultValue: "Type manually")
        static let pickFromListHelp = String(localized: "workflow.pickFromList.help", defaultValue: "Pick from list")
        static let hideInspectorHelp = String(localized: "workflow.hideInspector.help", defaultValue: "Hide inspector")
        static let showInspectorHelp = String(localized: "workflow.showInspector.help", defaultValue: "Show inspector")
        static let hideLogOutputHelp = String(localized: "workflow.hideLogOutput.help", defaultValue: "Hide output log")
        static let showLogOutputHelp = String(localized: "workflow.showLogOutput.help", defaultValue: "Show output log")
        static let inspectorEmptyLabel = String(localized: "workflow.inspectorEmpty.label", defaultValue: "Run a workflow to see results")

        static let timezoneFormatHelp = String(localized: "workflow.timezoneFormat.help", defaultValue: "Expected format: +HHMM or -HHMM")
        static let timezoneRequired = String(localized: "workflow.timezoneRequired", defaultValue: "Timezone required")
        static let deleteSourceWarning = String(localized: "workflow.deleteSource.warning",
            defaultValue: "Deletes processed files and companions from source after successful processing")

        // Help text
        static let groupHelp = String(localized: "workflow.group.help",
            defaultValue: "Optional group folder for organizing files (e.g. trip name like 'Japan'). Creates YYYY/Group/YYYY-MM-DD structure.")
        static let sourceDirHelp = String(localized: "workflow.sourceDir.help",
            defaultValue: "Directory to import from, usually an SD card mount point. Pre-filled from profile, editable.")
        static let copyCompanionHelp = String(localized: "workflow.copyCompanionFiles.help",
            defaultValue: "Companion files are sidecar files generated alongside the main media — e.g. .thm (thumbnail), .lrv (low-res proxy), .srt (subtitles/telemetry). When enabled, companions are copied alongside the main file to the ready directory.")
        static let sourceActionHelp = String(localized: "workflow.sourceAction.help",
            defaultValue: """
What happens to source files after processing:
• Archive — rename source folder with date suffix (default)
• Delete — remove only processed files and companions from source
""")
        static let appendTimezoneHelp = String(localized: "workflow.appendTimezoneToGroup.help",
            defaultValue: "Appends the timezone offset to the group folder name, e.g. 'Japan (+0900)'. Useful when a trip spans multiple timezones.")
        static let timezoneHelp = String(localized: "workflow.timezone.help",
            defaultValue: "Timezone the footage was shot in, used to fix timestamps for your video editor")
        static let timestampSourceLabel = String(localized: "workflow.timestampSource.label", defaultValue: "Source:")
        static let timestampSourceMetadata = String(localized: "workflow.timestampSource.metadata", defaultValue: "Metadata")
        static let timestampSourceFilenames = String(localized: "workflow.timestampSource.filenames", defaultValue: "From filenames")
        static let timeOffsetLabel = String(localized: "workflow.timeOffset.label", defaultValue: "Clock correction:")
        static let timeOffsetPlaceholder = String(localized: "workflow.timeOffset.placeholder", defaultValue: "seconds")
        static let timeOffsetHelp = String(localized: "workflow.timeOffset.help",
            defaultValue: "Shift all timestamps by this many seconds to correct camera clock drift. Positive = forward, negative = backward.")
        static let updateFilenameDatesToggle = String(localized: "workflow.updateFilenameDates.toggle", defaultValue: "Update filename dates")
        static let updateFilenameDatesHelp = String(localized: "workflow.updateFilenameDates.help",
            defaultValue: "Rename files to reflect corrected timestamps after fixing. Only affects files with parseable date patterns in their names.")
        static let timezoneManualHelp = String(localized: "workflow.timezoneManual.help",
            defaultValue: "Enter timezone manually in +HHMM or -HHMM format (e.g. +0900 for Japan)")
        static let dryRunHelp = String(localized: "workflow.dryRun.help",
            defaultValue: "Dry Run previews changes without modifying files. Apply performs the actual processing.")

        // Gyroflow settings
        static let maxZoomLabel = String(localized: "workflow.maxZoom.label", defaultValue: "Max zoom:")
        static let adaptiveZoomWindowLabel = String(localized: "workflow.adaptiveZoomWindow.label", defaultValue: "Zoom window:")
        static let adaptiveZoomMethodLabel = String(localized: "workflow.adaptiveZoomMethod.label", defaultValue: "Zoom method:")

        // Timezone conflict dialog
        static let timezoneConflictTitle = String(localized: "workflow.timezoneConflict.title",
            defaultValue: "Timezone Conflict")
        static let forceTimezoneButton = String(localized: "workflow.forceTimezone.button",
            defaultValue: "Override Timezone")

        static func mixedTimezonesMessage(groups: String) -> String {
            String(localized: "workflow.mixedTimezones.message",
                   defaultValue: "Files have different embedded timezones. Consider processing each group separately.\n\n\(groups)")
        }

        static func providedMismatchMessage(provided: String, existing: String) -> String {
            String(localized: "workflow.providedMismatch.message",
                   defaultValue: "You specified \(provided) but files have embedded timezone \(existing). The embedded timezone is usually correct (set by the camera). Override to use your timezone instead.")
        }
    }

    // MARK: - Profiles

    enum Profiles {
        static let selectPrompt = String(localized: "profiles.selectPrompt", defaultValue: "Select a profile to edit")
        static let nameLabel = String(localized: "profiles.name.label", defaultValue: "Name")
        static let namePlaceholder = String(localized: "profiles.name.placeholder", defaultValue: "profile-name")
        static let typeLabel = String(localized: "profiles.type.label", defaultValue: "Type")
        static let videoOption = String(localized: "profiles.video.option", defaultValue: "Video")
        static let photoOption = String(localized: "profiles.photo.option", defaultValue: "Photo")
        static let sourceDirLabel = String(localized: "profiles.sourceDir.label", defaultValue: "Source dir")
        static let readyDirLabel = String(localized: "profiles.readyDir.label", defaultValue: "Ready dir")
        static let exifMakeLabel = String(localized: "profiles.exifMake.label", defaultValue: "EXIF Make")
        static let exifModelLabel = String(localized: "profiles.exifModel.label", defaultValue: "EXIF Model")
        static let exifMakePlaceholder = String(localized: "profiles.exifMake.placeholder", defaultValue: "e.g. Sony")
        static let exifModelPlaceholder = String(localized: "profiles.exifModel.placeholder", defaultValue: "e.g. ILCE-7M4")
        static let fileTypesLabel = String(localized: "profiles.fileTypes.label", defaultValue: "File types")
        static let companionLabel = String(localized: "profiles.companion.label", defaultValue: "Companion")
        static let tagsLabel = String(localized: "profiles.tags.label", defaultValue: "Tags")
        static let tagPlaceholder = String(localized: "profiles.tag.placeholder", defaultValue: "tag1, tag2")
        static let gyroflowToggle = String(localized: "profiles.gyroflow.toggle", defaultValue: "Generate Gyroflow project files")
        static let saveButton = String(localized: "profiles.save.button", defaultValue: "Save")
        static let deleteConfirmationMessage = String(localized: "profiles.deleteConfirmation.message",
            defaultValue: "This will remove the profile from media-profiles.yaml. This cannot be undone.")

        static func deleteConfirmationTitle(_ name: String) -> String {
            String(localized: "profiles.deleteConfirmation.title",
                   defaultValue: "Delete profile \"\(name)\"?")
        }

        // Help text
        static let typeHelp = String(localized: "profiles.type.help",
            defaultValue: "Whether this profile handles photo or video files from the camera")
        static let companionHelp = String(localized: "profiles.companion.help",
            defaultValue: "Sidecar files generated alongside the main video — e.g. .thm (thumbnail), .lrv (low-res proxy), .srt (subtitle/telemetry). Imported together with the main file unless skipped.")
        static let gyroflowHelp = String(localized: "profiles.gyroflow.help",
            defaultValue: "Generate Gyroflow stabilization project files during pipeline processing. Requires the camera to record gyroscope data (e.g. GoPro, Insta360).")
        static let gyroflowMaxZoomLabel = String(localized: "profiles.gyroflow.maxZoom.label", defaultValue: "Max zoom:")
        static let gyroflowAdaptiveZoomWindowLabel = String(localized: "profiles.gyroflow.adaptiveZoomWindow.label", defaultValue: "Zoom window:")
        static let gyroflowAdaptiveZoomMethodLabel = String(localized: "profiles.gyroflow.adaptiveZoomMethod.label", defaultValue: "Zoom method:")
        static let fileExtensionsHelp = String(localized: "profiles.fileExtensions.help",
            defaultValue: "File types this profile processes (e.g. .mp4, .mov, .insv)")
        static let tagsHelp = String(localized: "profiles.tags.help",
            defaultValue: "macOS Finder tags applied to imported files for organization")

        static let unsavedChangesTitle = String(localized: "profiles.unsavedChanges.title",
            defaultValue: "You have unsaved changes")
        static let unsavedChangesMessage = String(localized: "profiles.unsavedChanges.message",
            defaultValue: "Your changes will be lost if you don't save them.")
        static let saveAndContinue = String(localized: "profiles.saveAndContinue.button",
            defaultValue: "Save Changes")
        static let discardChanges = String(localized: "profiles.discardChanges.button",
            defaultValue: "Discard Changes")
    }

    // MARK: - Settings

    enum Settings {
        static let licenseSection = String(localized: "settings.license.section", defaultValue: "License")
        static let scriptsSection = String(localized: "settings.scripts.section", defaultValue: "Scripts")
        static let proActivated = String(localized: "settings.pro.activated", defaultValue: "Jetlag Pro — Activated")
        static let planLabel = String(localized: "settings.plan.label", defaultValue: "Plan")
        static let scriptsDirLabel = String(localized: "settings.scriptsDir.label", defaultValue: "Scripts directory")
        static let profilesFilePlaceholder = String(localized: "settings.profilesFile.placeholder",
            defaultValue: "Profiles file (default: scripts_dir/media-profiles.yaml)")
        static let reloadProfilesButton = String(localized: "settings.reloadProfiles.button", defaultValue: "Reload Profiles")
        static let licenseKeyPlaceholder = String(localized: "settings.licenseKey.placeholder", defaultValue: "License key")
        static let activateButton = String(localized: "settings.activate.button", defaultValue: "Activate")
        static let activatingButton = String(localized: "settings.activating.button", defaultValue: "Activating…")
        static let buyProButton = String(localized: "settings.buyPro.button", defaultValue: "Buy Jetlag Pro")

        static func freePlan(fileLimit: Int) -> String {
            String(localized: "settings.freePlan",
                   defaultValue: "Free — up to \(fileLimit) files per run")
        }

        static func profilesLoaded(count: Int) -> String {
            String(localized: "settings.profilesLoaded",
                   defaultValue: "\(count) profiles loaded")
        }
    }

    // MARK: - Upgrade

    enum Upgrade {
        static let title = String(localized: "upgrade.title", defaultValue: "Jetlag Pro")
        static let subtitle = String(localized: "upgrade.subtitle", defaultValue: "Unlimited file processing")
        static let valueProp = String(localized: "upgrade.valueProp",
            defaultValue: "Unlock Jetlag Pro for unlimited processing — one-time purchase, no subscription.")
        static let alreadyPurchased = String(localized: "upgrade.alreadyPurchased", defaultValue: "Already purchased?")

        static func jobFileCount(_ count: Int) -> String {
            String(localized: "upgrade.jobFileCount",
                   defaultValue: "This job has \(count) files.")
        }

        static func freeLimit(fileLimit: Int) -> String {
            String(localized: "upgrade.freeLimit",
                   defaultValue: "The free version processes up to \(fileLimit) files per run.")
        }
    }

    // MARK: - Diff table

    enum DiffTable {
        static let title = String(localized: "diffTable.title", defaultValue: "Files")
        static let fileColumn = String(localized: "diffTable.file.column", defaultValue: "File")
        static let originalColumn = String(localized: "diffTable.original.column", defaultValue: "Original")
        static let correctedColumn = String(localized: "diffTable.corrected.column", defaultValue: "Corrected")
        static let timelineColumn = String(localized: "diffTable.timeline.column", defaultValue: "Timeline")
        static let timestampColumn = String(localized: "diffTable.timestamp.column", defaultValue: "Timestamp")
        static let destinationColumn = String(localized: "diffTable.destination.column", defaultValue: "Destination")
        static let statusColumn = String(localized: "diffTable.status.column", defaultValue: "Status")
        static let changedStatus = String(localized: "diffTable.changed.status", defaultValue: "Changed")
        static let noChangeStatus = String(localized: "diffTable.noChange.status", defaultValue: "No change")
        static let failedStatus = String(localized: "diffTable.failed.status", defaultValue: "Failed")
        static let wouldChangeStatus = String(localized: "diffTable.wouldChange.status", defaultValue: "Would change")
        static let wouldFixStatus = String(localized: "diffTable.wouldFix.status", defaultValue: "Would fix")
        static let wouldMoveStatus = String(localized: "diffTable.wouldMove.status", defaultValue: "Would move")
        static let fixedStatus = String(localized: "diffTable.fixed.status", defaultValue: "Fixed")
        static let movedStatus = String(localized: "diffTable.moved.status", defaultValue: "Moved")

        static let wouldFixChange = String(localized: "diffTable.wouldFix.change", defaultValue: "Would fix")
        static let fixedChange = String(localized: "diffTable.fixed.change", defaultValue: "Fixed")
        static let noChangeChange = String(localized: "diffTable.noChange.change", defaultValue: "No change")
        static let errorChange = String(localized: "diffTable.error.change", defaultValue: "Error")
        static let wouldFixAndMoveStatus = String(localized: "diffTable.wouldFixAndMove.status", defaultValue: "Would fix + move")
        static let fixedAndMovedStatus = String(localized: "diffTable.fixedAndMoved.status", defaultValue: "Fixed + moved")

        static func fileCount(_ count: Int) -> String {
            String(localized: "diffTable.fileCount",
                   defaultValue: "\(count) files")
        }
    }

    // MARK: - Log output

    enum LogOutput {
        static let title = String(localized: "logOutput.title", defaultValue: "Output")
        static let clearButton = String(localized: "logOutput.clear.button", defaultValue: "Clear")
        static let copyAllButton = String(localized: "logOutput.copyAll.button", defaultValue: "Copy All")

        static func lineCount(_ count: Int) -> String {
            String(localized: "logOutput.lineCount",
                   defaultValue: "\(count) lines")
        }
    }

    // MARK: - Errors

    enum Errors {
        static let profilesNotFound = String(localized: "error.profilesNotFound", defaultValue: "Profiles file not found")
        static let profilesUnreadable = String(localized: "error.profilesUnreadable", defaultValue: "Could not read profiles file")
        static let profilesInvalidYAML = String(localized: "error.profilesInvalidYAML", defaultValue: "Invalid YAML structure")
        static let profilesParseFailed = String(localized: "error.profilesParseFailed", defaultValue: "Failed to parse YAML")
        static let profilesWriteFailed = String(localized: "error.profilesWriteFailed", defaultValue: "Failed to write profiles")
        static let directoryNotFound = String(localized: "error.directoryNotFound", defaultValue: "Directory not found")
        static let pathIsFile = String(localized: "error.pathIsFile", defaultValue: "Path is a file, not a directory")
        static let licenseComingSoon = String(localized: "error.licenseComingSoon",
            defaultValue: "License activation coming soon — check back after launch")

        static func scriptStartFailed(_ description: String) -> String {
            String(localized: "error.scriptStartFailed",
                   defaultValue: "Failed to start: \(description)")
        }
    }
}
