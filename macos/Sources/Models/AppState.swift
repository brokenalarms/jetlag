import Foundation
import SwiftUI

enum SidebarTab: String, CaseIterable, Identifiable {
    case workflow = "Workflow"
    case profiles = "Profiles"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .workflow: "play.rectangle"
        case .profiles: "camera.on.rectangle"
        }
    }
}

enum SourceAction: String, CaseIterable {
    case archive, delete
}

enum PipelineStep: String, CaseIterable, Identifiable {
    case ingest = "Ingest"
    case tag = "Tag"
    case fixTimezone = "Fix Timezone"
    case organize = "Organize"
    case gyroflow = "Gyroflow"
    case archiveSource = "Archive Source"

    var id: String { rawValue }

    var isAlwaysOn: Bool {
        self == .ingest || self == .organize
    }

    var systemImage: String {
        switch self {
        case .ingest: "sdcard"
        case .tag: "tag"
        case .fixTimezone: "clock.arrow.2.circlepath"
        case .organize: "folder.badge.gearshape"
        case .gyroflow: "gyroscope"
        case .archiveSource: "archivebox"
        }
    }

    var iconColor: Color {
        switch self {
        case .ingest:        Color("NeonCyan")
        case .tag:           Color("NeonPink")
        case .fixTimezone:   Color("NeonYellow")
        case .organize:      Color.accentColor
        case .gyroflow:      Color("NeonPurple")
        case .archiveSource: Color("NeonCyan")
        }
    }

    var help: String {
        switch self {
        case .ingest: "Copy files from source to working directory for processing"
        case .tag: "Apply Finder tags and EXIF metadata from profile"
        case .fixTimezone: "Correct timestamps for your video editor using the selected timezone"
        case .organize: "Move processed files into date-based folders in ready directory"
        case .gyroflow: "Generate Gyroflow stabilization project files (requires gyro data)"
        case .archiveSource: "Act on source folder after processing (archive or delete)"
        }
    }
}

struct LogLine: Identifiable {
    let id = UUID()
    let text: String
    let stream: Stream

    enum Stream {
        case stdout, stderr
    }

    var isMachineReadable: Bool {
        text.hasPrefix("@@")
    }
}

@Observable
final class AppState {
    var selectedTab: SidebarTab = .workflow

    let scriptsDirectory: String
    var profilesFilePath: String {
        didSet { UserDefaults.standard.set(profilesFilePath, forKey: "profilesFilePath") }
    }

    var profilesConfig: ProfilesConfig?
    var profileLoadError: ProfileLoadError?

    var sortedProfileNames: [String] {
        profilesConfig?.profiles.keys.sorted() ?? []
    }

    // Workflow state
    var selectedProfile: String = ""
    var group: String = ""
    var sourceDir: String = ""
    var timezone: String = ""
    var useTimezonePicker: Bool = true
    var copyCompanionFiles: Bool = false
    var sourceAction: SourceAction = .archive
    var appendTimezoneToGroup: Bool = false
    var applyMode: Bool = false

    var showLog: Bool = false
    var enabledSteps: Set<PipelineStep> = Set(PipelineStep.allCases) {
        didSet {
            if !enabledSteps.contains(.archiveSource) {
                sourceAction = .archive
            }
        }
    }

    // Execution state
    var isRunning: Bool = false
    var logOutput: [LogLine] = []
    var currentProcess: Process?

    init() {
        self.scriptsDirectory = (Bundle.main.resourcePath! as NSString)
            .appendingPathComponent("scripts")
        self.profilesFilePath = UserDefaults.standard.string(forKey: "profilesFilePath") ?? ""
    }

    var resolvedProfilesPath: String {
        if profilesFilePath.isEmpty {
            return (scriptsDirectory as NSString).appendingPathComponent("media-profiles.yaml")
        }
        return profilesFilePath
    }

    var activeProfile: MediaProfile? {
        profilesConfig?.profiles[selectedProfile]
    }

    func profile(named name: String) -> MediaProfile? {
        profilesConfig?.profiles[name]
    }

    var availableSteps: [PipelineStep] {
        guard let profile = activeProfile else { return [] }
        var steps: [PipelineStep] = [.ingest, .tag, .fixTimezone, .organize]
        if profile.gyroflowEnabled == true {
            steps.append(.gyroflow)
        }
        steps.append(.archiveSource)
        return steps
    }

    func resetWorkflowFields(for profileName: String) {
        group = ""
        timezone = ""
        useTimezonePicker = true
        copyCompanionFiles = false
        sourceAction = .archive
        appendTimezoneToGroup = false
        applyMode = false
        if let profile = profile(named: profileName) {
            sourceDir = profile.sourceDir ?? ""
        } else {
            sourceDir = ""
        }
        enabledSteps = Set(availableSteps)
    }

    func buildPipelineArgs() -> (script: String, args: [String]) {
        var args: [String] = []
        args += ["--profile", selectedProfile]
        args += ["--source", sourceDir]

        if !group.isEmpty {
            args += ["--group", group]
        }
        if appendTimezoneToGroup {
            args.append("--append-timezone-to-group")
        }

        let optionalSteps = enabledSteps.filter { !$0.isAlwaysOn }
        let taskNames: [PipelineStep: String] = [
            .tag: "tag",
            .fixTimezone: "fix-timestamp",
            .gyroflow: "gyroflow",
            .archiveSource: "archive-source",
        ]
        let tasks = availableSteps
            .filter { optionalSteps.contains($0) }
            .compactMap { taskNames[$0] }
        if !tasks.isEmpty {
            args += ["--tasks"] + tasks
        }

        if enabledSteps.contains(.archiveSource) && sourceAction != .archive {
            args += ["--source-action", sourceAction.rawValue]
        }

        if copyCompanionFiles {
            args.append("--copy-companion-files")
        }
        if enabledSteps.contains(.fixTimezone) && !timezone.isEmpty {
            args += ["--timezone", timezone]
        }
        if applyMode {
            args.append("--apply")
        }

        return (script: "media-pipeline.sh", args: args)
    }

    func clearLog() {
        logOutput = []
    }

    func appendLog(_ line: LogLine) {
        logOutput.append(line)
    }

    func cancelRunning() {
        currentProcess?.terminate()
        currentProcess = nil
        isRunning = false
    }
}
