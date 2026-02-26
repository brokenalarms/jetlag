import Foundation
import SwiftUI

enum SidebarTab: String, CaseIterable, Identifiable {
    case workflow = "Workflow"
    case profiles = "Profiles"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .workflow: Strings.Nav.workflow
        case .profiles: Strings.Nav.profiles
        }
    }

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

    var label: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestLabel
        case .tag: Strings.Pipeline.tagLabel
        case .fixTimezone: Strings.Pipeline.fixTimezoneLabel
        case .organize: Strings.Pipeline.organizeLabel
        case .gyroflow: Strings.Pipeline.gyroflowLabel
        case .archiveSource: Strings.Pipeline.archiveSourceLabel
        }
    }

    var help: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestHelp
        case .tag: Strings.Pipeline.tagHelp
        case .fixTimezone: Strings.Pipeline.fixTimezoneHelp
        case .organize: Strings.Pipeline.organizeHelp
        case .gyroflow: Strings.Pipeline.gyroflowHelp
        case .archiveSource: Strings.Pipeline.archiveSourceHelp
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
final class WorkflowSession {
    var profileName: String
    var workingProfile: MediaProfile

    var sourceDir: Dirtyable<String>
    var readyDir: Dirtyable<String>
    var tags: Dirtyable<[String]?>
    var timezone: Dirtyable<String>

    var group: String = ""
    var useTimezonePicker: Bool = true
    var copyCompanionFiles: Bool = false
    var sourceAction: SourceAction = .archive
    var appendTimezoneToGroup: Bool = false
    var applyMode: Bool = false

    var enabledSteps: Set<PipelineStep> = [] {
        didSet {
            if !enabledSteps.contains(.archiveSource) {
                sourceAction = .archive
            }
        }
    }

    init(profile: MediaProfile? = nil, profileName: String = "") {
        self.profileName = profileName
        self.workingProfile = profile ?? MediaProfile()
        self.sourceDir = Dirtyable(profile?.sourceDir ?? "")
        self.readyDir = Dirtyable(profile?.readyDir ?? "")
        self.tags = Dirtyable(profile?.tags)
        self.timezone = Dirtyable("")
        self.enabledSteps = Set(Self.computeAvailableSteps(profile: profile))
    }

    var availableSteps: [PipelineStep] {
        Self.computeAvailableSteps(profile: workingProfile)
    }

    private static func computeAvailableSteps(profile: MediaProfile?) -> [PipelineStep] {
        guard let profile else { return [] }
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
            return !sourceDir.current.isEmpty
        case .organize:
            return !readyDir.current.isEmpty
        case .fixTimezone:
            return !timezone.current.isEmpty
        case .tag, .gyroflow, .archiveSource:
            return true
        }
    }

    func validateTimezone() -> String? {
        if useTimezonePicker { return nil }
        if !enabledSteps.contains(.fixTimezone) { return nil }
        if timezone.current.isEmpty { return Strings.Workflow.timezoneRequired }
        if !timezone.current.contains(/^[+-]\d{4}$/) { return Strings.Workflow.timezoneFormatHelp }
        return nil
    }

    var allStepsReady: Bool {
        let active = availableSteps.filter { $0.isAlwaysOn || enabledSteps.contains($0) }
        let stepsReady = active.allSatisfy { isStepReady($0) }
        let fieldsValid = validateDirectory(sourceDir.current) == nil
            && validateDirectory(readyDir.current) == nil
            && validateTimezone() == nil
        return stepsReady && fieldsValid
    }

    func buildPipelineArgs() -> (script: String, args: [String]) {
        var args: [String] = []
        args += ["--profile", profileName]
        args += ["--source", sourceDir.current]
        args += ["--target", readyDir.current]

        let tagList = (tags.current ?? []).filter { !$0.isEmpty }.joined(separator: ",")
        if !tagList.isEmpty {
            args += ["--tags", tagList]
        }
        if let make = workingProfile.exif?.make, !make.isEmpty {
            args += ["--make", make]
        }
        if let model = workingProfile.exif?.model, !model.isEmpty {
            args += ["--model", model]
        }

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
        if enabledSteps.contains(.fixTimezone) && !timezone.current.isEmpty {
            args += ["--timezone", timezone.current]
        }
        if applyMode {
            args.append("--apply")
        }

        return (script: "media-pipeline.sh", args: args)
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

    var workflowSession = WorkflowSession()

    var showLog: Bool = false

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
        workflowSession.profileName.isEmpty ? nil : workflowSession.workingProfile
    }

    func profile(named name: String) -> MediaProfile? {
        profilesConfig?.profiles[name]
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
        let normalized: String? = value.isEmpty ? nil : value

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
            currentDiffRow?.tagAction = normalized
        case "tags_added":
            currentDiffRow?.tagsAdded = normalized
        case "original_time":
            currentDiffRow?.originalTime = normalized
        case "corrected_time":
            currentDiffRow?.correctedTime = normalized
        case "timestamp_source":
            currentDiffRow?.timestampSource = normalized
        case "timestamp_action":
            currentDiffRow?.timestampAction = normalized
        case "timezone":
            currentDiffRow?.timezone = normalized
        case "dest":
            currentDiffRow?.dest = normalized
        case "action":
            currentDiffRow?.organizeAction = normalized
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
