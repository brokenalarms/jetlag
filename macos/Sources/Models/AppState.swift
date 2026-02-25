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
    var diffTableRows: [DiffTableRow] = []
    private var currentDiffRow: DiffTableRow?

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

    func isStepReady(_ step: PipelineStep) -> Bool {
        switch step {
        case .ingest:
            return !sourceDir.isEmpty
        case .fixTimezone:
            return !timezone.isEmpty
        case .tag, .organize, .gyroflow, .archiveSource:
            return true
        }
    }

    var allStepsReady: Bool {
        let active = availableSteps.filter { $0.isAlwaysOn || enabledSteps.contains($0) }
        return active.allSatisfy { isStepReady($0) }
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
        diffTableRows = []
        currentDiffRow = nil
    }

    func appendLog(_ line: LogLine) {
        if line.isMachineReadable {
            parseMachineReadableLine(line.text)
            return
        }
        logOutput.append(line)
    }

    private func parseMachineReadableLine(_ text: String) {
        let stripped = String(text.dropFirst(2))
        guard let eqIndex = stripped.firstIndex(of: "=") else { return }
        let key = String(stripped[stripped.startIndex..<eqIndex])
        let value = String(stripped[stripped.index(after: eqIndex)...])

        switch key {
        case "pipeline_file":
            if var row = currentDiffRow {
                row.pipelineResult = row.pipelineResult ?? "in_progress"
                diffTableRows.append(row)
            }
            currentDiffRow = DiffTableRow(file: value)
        case "pipeline_result":
            if var row = currentDiffRow {
                row.pipelineResult = value
                diffTableRows.append(row)
                currentDiffRow = nil
            }
        case "tag_action":
            currentDiffRow?.tagAction = value
        case "tags_added":
            currentDiffRow?.tagsAdded = value
        case "original_time":
            currentDiffRow?.originalTime = value
        case "corrected_time":
            currentDiffRow?.correctedTime = value
        case "timestamp_source":
            currentDiffRow?.timestampSource = value
        case "timestamp_action":
            currentDiffRow?.timestampAction = value
        case "timezone":
            currentDiffRow?.timezone = value
        case "dest":
            currentDiffRow?.dest = value
        case "action":
            currentDiffRow?.organizeAction = value
        default:
            break
        }
    }

    func cancelRunning() {
        currentProcess?.terminate()
        currentProcess = nil
        isRunning = false
    }
}
