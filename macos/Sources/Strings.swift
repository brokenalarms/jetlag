import Foundation

enum Strings {
    enum Workflow {
        static let subfolder = String(localized: "workflow.subfolder.help",
            defaultValue: "Optional subfolder for organizing files (e.g. trip or project name)")
        static let sourceDir = String(localized: "workflow.sourceDir.help",
            defaultValue: "Directory to import from, usually an SD card mount point. Pre-filled from profile, editable.")
        static let skipCompanion = String(localized: "workflow.skipCompanion.help",
            defaultValue: "Companion files are sidecar files generated alongside the main media — e.g. .thm (thumbnail), .lrv (low-res proxy), .srt (subtitles/telemetry). When skipped, only the primary media files are imported. The companion files remain on the source and are not deleted.")
        static let preserveSource = String(localized: "workflow.preserveSource.help",
            defaultValue: """
When enabled, original are left in place on the memory card after copying.

When disabled, files are archived on the card (e.g., moved into 'DCIM - copied 2026-01-01' after successful copy).

Files will not be deleted from the memory card in either case.
""")
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
