import Foundation

enum Strings {
    enum Workflow {
        static let group = String(localized: "workflow.group.help",
            defaultValue: "Optional group folder for organizing files (e.g. trip name like 'Japan'). Creates YYYY/Group/YYYY-MM-DD structure.")
        static let sourceDir = String(localized: "workflow.sourceDir.help",
            defaultValue: "Directory to import from, usually an SD card mount point. Pre-filled from profile, editable.")
        static let copyCompanionFiles = String(localized: "workflow.copyCompanionFiles.help",
            defaultValue: "Companion files are sidecar files generated alongside the main media — e.g. .thm (thumbnail), .lrv (low-res proxy), .srt (subtitles/telemetry). When enabled, companions are copied alongside the main file to the ready directory.")
        static let sourceAction = String(localized: "workflow.sourceAction.help",
            defaultValue: """
What happens to source files after processing:
• Archive — rename source folder with date suffix (default)
• Delete — remove only processed files and companions from source
""")
        static let appendTimezoneToGroup = String(localized: "workflow.appendTimezoneToGroup.help",
            defaultValue: "Appends the timezone offset to the group folder name, e.g. 'Japan (+0900)'. Useful when a trip spans multiple timezones.")
        static let timezone = String(localized: "workflow.timezone.help",
            defaultValue: "Timezone the footage was shot in, used to fix timestamps for your video editor")
        static let timezoneManual = String(localized: "workflow.timezoneManual.help",
            defaultValue: "Enter timezone manually in +HHMM or -HHMM format (e.g. +0900 for Japan)")
        static let dryRun = String(localized: "workflow.dryRun.help",
            defaultValue: "Dry Run previews changes without modifying files. Apply performs the actual processing.")
    }

    enum Profiles {
        static let type = String(localized: "profiles.type.help",
            defaultValue: "Whether this profile handles photo or video files from the camera")
        static let companion = String(localized: "profiles.companion.help",
            defaultValue: "Sidecar files generated alongside the main video — e.g. .thm (thumbnail), .lrv (low-res proxy), .srt (subtitle/telemetry). Imported together with the main file unless skipped.")
        static let gyroflow = String(localized: "profiles.gyroflow.help",
            defaultValue: "Generate Gyroflow stabilization project files during pipeline processing. Requires the camera to record gyroscope data (e.g. GoPro, Insta360).")
        static let fileExtensions = String(localized: "profiles.fileExtensions.help",
            defaultValue: "File types this profile processes (e.g. .mp4, .mov, .insv)")
        static let tags = String(localized: "profiles.tags.help",
            defaultValue: "macOS Finder tags applied to imported files for organization")
    }
}
