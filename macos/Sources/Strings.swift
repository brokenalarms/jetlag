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
        static let requiredLabel = String(localized: "workflow.required.label", defaultValue: "Required")
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
        static let inspectorStartingLabel = String(localized: "workflow.inspectorStarting.label", defaultValue: "Scanning files…")

        static let timezoneUnknown = String(localized: "workflow.timezoneUnknown", defaultValue: "Unrecognized timezone")
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

        // Fix Timestamps preview
        static let fixTimestampSourceFilenamesHint = String(localized: "workflow.fixTimestampPreview.sourceFilenames",
            defaultValue: "Use filename dates as timestamp source")
        static let fixTimestampRenameHint = String(localized: "workflow.fixTimestampPreview.rename",
            defaultValue: "Rename files to match corrected dates")

        static func fixTimestampShiftHint(sign: String, offset: Int) -> String {
            String(localized: "workflow.fixTimestampPreview.shift",
                   defaultValue: "Shift timestamps by \(sign)\(offset)s")
        }

        static func fixTimestampSourceFilenamesZoneHint(city: String, offsetLabel: String) -> String {
            String(localized: "workflow.fixTimestampPreview.sourceFilenamesZone",
                   defaultValue: "Use filename dates as \(city) local time (\(offsetLabel))")
        }

        static func fixTimestampSourceFilenamesZoneMultiHint(city: String) -> String {
            String(localized: "workflow.fixTimestampPreview.sourceFilenamesZoneMulti",
                   defaultValue: "Use filename dates as \(city) local time, resolved per file")
        }

        static func fixTimestampZoneHint(city: String, offsetLabel: String) -> String {
            String(localized: "workflow.fixTimestampPreview.zone",
                   defaultValue: "Apply \(city) time (\(offsetLabel))")
        }

        static func fixTimestampZoneMultiHint(city: String) -> String {
            String(localized: "workflow.fixTimestampPreview.zoneMulti",
                   defaultValue: "Apply \(city) time, resolved per file")
        }

        // Timezone conflict dialog
        static let timezoneConflictTitle = String(localized: "workflow.timezoneConflict.title",
            defaultValue: "Timezone Conflict")
        static let forceTimezoneButton = String(localized: "workflow.forceTimezone.button",
            defaultValue: "Override Timezone")

        // Organize conflict dialog
        static let overwriteConflictTitle = String(localized: "workflow.overwriteConflict.title",
            defaultValue: "Files Already at Destination")
        static let overwriteButton = String(localized: "workflow.overwrite.button",
            defaultValue: "Overwrite")

        static func overwriteConflictMessage(count: Int) -> String {
            count == 1
                ? String(localized: "workflow.overwriteConflict.message.one",
                         defaultValue: "1 file already exists at the destination with different contents. Overwrite it?")
                : String(localized: "workflow.overwriteConflict.message.many",
                         defaultValue: "\(count) files already exist at the destination with different contents. Overwrite them?")
        }

        // Unpreviewed apply dialog
        static let dryRunStaleTitle = String(localized: "workflow.dryRunStale.title",
            defaultValue: "Settings Changed Since the Last Dry Run")
        static let noDryRunTitle = String(localized: "workflow.noDryRun.title",
            defaultValue: "No Dry Run Yet")
        static let dryRunStaleMessage = String(localized: "workflow.dryRunStale.message",
            defaultValue: "The table is a preview of different settings. Applying now moves and replaces files against a plan you have not seen.")
        static let noDryRunMessage = String(localized: "workflow.noDryRun.message",
            defaultValue: "Nothing has been previewed. Applying now moves and replaces files against a plan you have not seen.")
        static let dryRunFirstButton = String(localized: "workflow.dryRunFirst.button",
            defaultValue: "Dry Run First")
        static let applyAnywayButton = String(localized: "workflow.applyAnyway.button",
            defaultValue: "Apply Anyway")

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
        static let gyroflowUnavailable = String(localized: "profiles.gyroflow.unavailable",
            defaultValue: "Install Gyroflow in Settings to enable stabilization.")
        static let fileExtensionsHelp = String(localized: "profiles.fileExtensions.help",
            defaultValue: "File types this profile processes (e.g. .mp4, .mov, .insv)")
        static let tagsHelp = String(localized: "profiles.tags.help",
            defaultValue: "macOS Finder tags applied to imported files for organization")

        static let maxZoomLabel = String(localized: "profiles.maxZoom.label", defaultValue: "Max zoom")
        static let maxZoomHelp = String(localized: "profiles.maxZoom.help",
            defaultValue: "Maximum zoom factor (percentage) Gyroflow can apply to stabilize footage. Higher values allow more aggressive stabilization but crop more of the frame.")
        static let adaptiveZoomWindowLabel = String(localized: "profiles.adaptiveZoomWindow.label", defaultValue: "Zoom window")
        static let adaptiveZoomWindowHelp = String(localized: "profiles.adaptiveZoomWindow.help",
            defaultValue: "Time window in seconds over which adaptive zoom smooths its adjustments. Longer windows produce smoother zoom transitions.")
        static let adaptiveZoomMethodLabel = String(localized: "profiles.adaptiveZoomMethod.label", defaultValue: "Zoom method")
        static let adaptiveZoomMethodHelp = String(localized: "profiles.adaptiveZoomMethod.help",
            defaultValue: "How Gyroflow adapts zoom level: None disables adaptive zoom, Dynamic adjusts zoom per-frame based on motion, Static uses a fixed crop.")
        static let zoomMethodNone = String(localized: "profiles.zoomMethod.none", defaultValue: "None")
        static let zoomMethodDynamic = String(localized: "profiles.zoomMethod.dynamic", defaultValue: "Dynamic")
        static let zoomMethodStatic = String(localized: "profiles.zoomMethod.static", defaultValue: "Static")

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
        static let profilesFileLabel = String(localized: "settings.profilesFile.label", defaultValue: "Profiles file")
        static func profilesFilePlaceholder(defaultPath: String) -> String {
            String(localized: "settings.profilesFile.placeholder",
                   defaultValue: "Default: \(defaultPath)")
        }
        static let profilesFileHelp = String(localized: "settings.profilesFile.help",
            defaultValue: "Leave empty to use the file above. Set it to point the app at another profiles file, such as a repository checkout.")
        static let reloadProfilesButton = String(localized: "settings.reloadProfiles.button", defaultValue: "Reload Profiles")
        static let licenseKeyPlaceholder = String(localized: "settings.licenseKey.placeholder", defaultValue: "License key")
        static let activateButton = String(localized: "settings.activate.button", defaultValue: "Activate")
        static let activatingButton = String(localized: "settings.activating.button", defaultValue: "Activating…")
        static let buyProButton = String(localized: "settings.buyPro.button", defaultValue: "Buy Jetlag Pro")
        static let debugUnlockToggle = String(localized: "settings.debugUnlock.toggle", defaultValue: "Unlock Pro (debug builds only)")

        static let gyroflowSection = String(localized: "settings.gyroflow.section", defaultValue: "Stabilization (Gyroflow)")
        static let gyroflowInstalled = String(localized: "settings.gyroflow.installed", defaultValue: "Gyroflow installed")
        static let gyroflowMissing = String(localized: "settings.gyroflow.missing",
            defaultValue: "Gyroflow is not installed — stabilization options are hidden")
        static let gyroflowInstallButton = String(localized: "settings.gyroflow.install.button", defaultValue: "Install Gyroflow")
        static let gyroflowInstallingButton = String(localized: "settings.gyroflow.installing.button", defaultValue: "Installing…")
        static let gyroflowDownloadNote = String(localized: "settings.gyroflow.downloadNote",
            defaultValue: "Downloads Gyroflow (about 200 MB) and installs it alongside Jetlag.")
        static let gyroflowSourceApplications = String(localized: "settings.gyroflow.source.applications", defaultValue: "/Applications")
        static let gyroflowSourceJetlag = String(localized: "settings.gyroflow.source.jetlag", defaultValue: "installed by Jetlag")
        static let gyroflowSourcePath = String(localized: "settings.gyroflow.source.path", defaultValue: "found on PATH")
        static let gyroflowSourceLabel = String(localized: "settings.gyroflow.source.label", defaultValue: "Location")

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
        static let wouldCopyStatus = String(localized: "diffTable.wouldCopy.status", defaultValue: "Would copy")
        static let wouldMoveStatus = String(localized: "diffTable.wouldMove.status", defaultValue: "Would move")
        static let fixedStatus = String(localized: "diffTable.fixed.status", defaultValue: "Fixed")
        static let copiedStatus = String(localized: "diffTable.copied.status", defaultValue: "Copied")
        static let movedStatus = String(localized: "diffTable.moved.status", defaultValue: "Moved")
        static let moveSkippedStatus = String(localized: "diffTable.moveSkipped.status", defaultValue: "Move skipped")
        static let moveFailedStatus = String(localized: "diffTable.moveFailed.status", defaultValue: "Move failed")

        /// A file the destination already held, replaced. "at destination" is what
        /// separates it from a plain copy: something that was there is gone.
        static let overwroteStatus = String(
            localized: "diffTable.overwrote.status", defaultValue: "Replaced at destination")
        static let wouldOverwriteStatus = String(
            localized: "diffTable.wouldOverwrite.status", defaultValue: "Would replace at destination")

        /// A dry run's conflicting file, standalone: what Apply will actually do — prompt,
        /// then replace — not what "skipped" would suggest on its own.
        static let wouldReplaceStatus = String(
            localized: "diffTable.wouldReplace.status", defaultValue: "Would replace at destination (asks first)")

        // The same outcomes phrased to follow a correction, as in "Would fix + copy".
        static let wouldCopyStatusAfterFix = String(localized: "diffTable.wouldCopy.afterFix", defaultValue: "copy")
        static let wouldMoveStatusAfterFix = String(localized: "diffTable.wouldMove.afterFix", defaultValue: "move")
        static let copiedStatusAfterFix = String(localized: "diffTable.copied.afterFix", defaultValue: "copied")
        static let movedStatusAfterFix = String(localized: "diffTable.moved.afterFix", defaultValue: "moved")
        static let moveSkippedStatusAfterFix = String(localized: "diffTable.moveSkipped.afterFix", defaultValue: "move skipped")
        static let moveFailedStatusAfterFix = String(localized: "diffTable.moveFailed.afterFix", defaultValue: "move failed")
        static let overwroteStatusAfterFix = String(
            localized: "diffTable.overwrote.afterFix", defaultValue: "replaced at destination")
        static let wouldOverwriteStatusAfterFix = String(
            localized: "diffTable.wouldOverwrite.afterFix", defaultValue: "replace at destination")
        static let wouldReplaceStatusAfterFix = String(
            localized: "diffTable.wouldReplace.afterFix", defaultValue: "replace at destination (asks first)")

        static func combinedStatus(_ correction: String, _ movement: String) -> String {
            String(localized: "diffTable.combined.status", defaultValue: "\(correction) + \(movement)")
        }

        /// A dry run's identical-file conflict: nothing to apply, so it reads as a fact
        /// rather than a pending action — "·" instead of "+" marks that difference.
        static func wouldFixIdenticalStatus(_ correction: String) -> String {
            String(localized: "diffTable.wouldFixIdentical.status",
                   defaultValue: "\(correction) · destination already has it")
        }

        static let skipIdenticalHelp = String(
            localized: "diffTable.skip.identical.help",
            defaultValue: "An identical copy is already at the destination.")
        static let skipExistsDiffersHelp = String(
            localized: "diffTable.skip.existsDiffers.help",
            defaultValue: "A different file of the same name is already at the destination. Nothing was moved.")
        static let skipUserChoiceHelp = String(
            localized: "diffTable.skip.userChoice.help",
            defaultValue: "You chose to keep the file already at the destination.")

        static let sourceDateTimeOriginal = String(localized: "diffTable.source.dateTimeOriginal", defaultValue: "DateTimeOriginal")
        static let sourceCreationDate = String(localized: "diffTable.source.creationDate", defaultValue: "Keys:CreationDate")
        static let sourceClockUTC = String(localized: "diffTable.source.clockUTC", defaultValue: "clock (UTC)")
        static let sourceFilename = String(localized: "diffTable.source.filename", defaultValue: "filename")
        static let sourceFileTime = String(localized: "diffTable.source.fileTime", defaultValue: "file time")
        static let utcSuffix = String(localized: "diffTable.utc.suffix", defaultValue: "UTC")

        static func sourceHelp(_ label: String) -> String {
            String(localized: "diffTable.source.help", defaultValue: "Source: \(label)")
        }

        static func wouldWrite(_ fields: String) -> String {
            String(localized: "diffTable.wouldWrite", defaultValue: "Writes \(fields)")
        }

        static let showInFinder = String(localized: "diffTable.showInFinder", defaultValue: "Show in Finder")
        static let quickLook = String(localized: "diffTable.quickLook", defaultValue: "Quick Look")
        static let showExistingAtDestination = String(
            localized: "diffTable.showExistingAtDestination",
            defaultValue: "Show Existing File at Destination")

        static let wouldFixChange = String(localized: "diffTable.wouldFix.change", defaultValue: "Would fix")
        static let fixedChange = String(localized: "diffTable.fixed.change", defaultValue: "Fixed")
        static let noChangeChange = String(localized: "diffTable.noChange.change", defaultValue: "No change")
        static let errorChange = String(localized: "diffTable.error.change", defaultValue: "Error")
        static let requiresForceTimezoneHelp = String(
            localized: "diffTable.requiresForceTimezone.help",
            defaultValue: "This file already carries a timezone from the camera. Applying relabels it, and needs confirmation.")

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
        static let cancelled = String(localized: "logOutput.cancelled", defaultValue: "Cancelled")

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
        static let profilesSeedFailed = String(localized: "error.profilesSeedFailed", defaultValue: "Could not create the profiles file")
        static let directoryNotFound = String(localized: "error.directoryNotFound", defaultValue: "Directory not found")
        static let pathIsFile = String(localized: "error.pathIsFile", defaultValue: "Path is a file, not a directory")
        static let licenseComingSoon = String(localized: "error.licenseComingSoon",
            defaultValue: "License activation coming soon — check back after launch")
        static let commandLineToolsTitle = String(localized: "error.commandLineTools.title",
            defaultValue: "Command Line Tools required")
        static let commandLineToolsMissing = String(localized: "error.commandLineTools.message",
            defaultValue: """
            Jetlag runs its pipeline on the Python that ships with macOS, which needs the Xcode \
            Command Line Tools. Install them by running this in Terminal:

            xcode-select --install
            """)

        static func scriptStartFailed(_ description: String) -> String {
            String(localized: "error.scriptStartFailed",
                   defaultValue: "Failed to start: \(description)")
        }
    }
}
