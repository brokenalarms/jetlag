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
    case fixTimestamps = "Fix Timestamps"
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
        case .fixTimestamps: "clock.arrow.2.circlepath"
        case .organize: "folder.badge.gearshape"
        case .gyroflow: "gyroscope"
        case .archiveSource: "archivebox"
        }
    }

    var iconColor: Color {
        switch self {
        case .ingest:        Color("NeonCyan")
        case .tag:           Color("NeonPink")
        case .fixTimestamps:   Color("NeonYellow")
        case .organize:      Color.accentColor
        case .gyroflow:      Color("NeonPurple")
        case .archiveSource: Color("NeonCyan")
        }
    }

    var label: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestLabel
        case .tag: Strings.Pipeline.tagLabel
        case .fixTimestamps: Strings.Pipeline.fixTimestampsLabel
        case .organize: Strings.Pipeline.organizeLabel
        case .gyroflow: Strings.Pipeline.gyroflowLabel
        case .archiveSource: Strings.Pipeline.archiveSourceLabel
        }
    }

    var help: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestHelp
        case .tag: Strings.Pipeline.tagHelp
        case .fixTimestamps: Strings.Pipeline.fixTimestampsHelp
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
        text.hasPrefix("{")
    }
}

/// JSONL event types emitted by media-pipeline.py on stdout.
enum PipelineEvent: Decodable {
    case pipelineFile(file: String)
    case stageComplete(stage: String)
    case tagResult(file: String, action: String, tagsAdded: [String],
                   exifMake: String, exifModel: String)
    case timestampResult(file: String, action: String,
                         originalTime: String?, correctedTime: String?,
                         source: String?, timezone: String?,
                         correctionMode: String?,
                         timeOffsetSeconds: Int?,
                         timeOffsetDisplay: String?)
    case renameResult(file: String, renamedTo: String)
    case organizeResult(file: String, action: String, dest: String)
    case gyroflowResult(file: String, action: String, gyroflowPath: String,
                        error: String?)
    case pipelineResult(file: String, result: String)

    private enum CodingKeys: String, CodingKey {
        case event, file, stage, action
        case tagsAdded = "tags_added"
        case exifMake = "exif_make"
        case exifModel = "exif_model"
        case originalTime = "original_time"
        case correctedTime = "corrected_time"
        case source, timezone
        case correctionMode = "correction_mode"
        case timeOffsetSeconds = "time_offset_seconds"
        case timeOffsetDisplay = "time_offset_display"
        case renamedTo = "renamed_to"
        case dest
        case gyroflowPath = "gyroflow_path"
        case error, result
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let event = try container.decode(String.self, forKey: .event)

        switch event {
        case "pipeline_file":
            self = .pipelineFile(
                file: try container.decode(String.self, forKey: .file))
        case "stage_complete":
            self = .stageComplete(
                stage: try container.decode(String.self, forKey: .stage))
        case "tag_result":
            self = .tagResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                tagsAdded: try container.decode([String].self, forKey: .tagsAdded),
                exifMake: try container.decode(String.self, forKey: .exifMake),
                exifModel: try container.decode(String.self, forKey: .exifModel))
        case "timestamp_result":
            self = .timestampResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                originalTime: try container.decodeIfPresent(String.self, forKey: .originalTime),
                correctedTime: try container.decodeIfPresent(String.self, forKey: .correctedTime),
                source: try container.decodeIfPresent(String.self, forKey: .source),
                timezone: try container.decodeIfPresent(String.self, forKey: .timezone),
                correctionMode: try container.decodeIfPresent(String.self, forKey: .correctionMode),
                timeOffsetSeconds: try container.decodeIfPresent(Int.self, forKey: .timeOffsetSeconds),
                timeOffsetDisplay: try container.decodeIfPresent(String.self, forKey: .timeOffsetDisplay))
        case "rename_result":
            self = .renameResult(
                file: try container.decode(String.self, forKey: .file),
                renamedTo: try container.decode(String.self, forKey: .renamedTo))
        case "organize_result":
            self = .organizeResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                dest: try container.decode(String.self, forKey: .dest))
        case "gyroflow_result":
            self = .gyroflowResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                gyroflowPath: try container.decode(String.self, forKey: .gyroflowPath),
                error: try container.decodeIfPresent(String.self, forKey: .error))
        case "pipeline_result":
            self = .pipelineResult(
                file: try container.decode(String.self, forKey: .file),
                result: try container.decode(String.self, forKey: .result))
        default:
            throw DecodingError.dataCorruptedError(
                forKey: .event, in: container,
                debugDescription: "Unknown event type: \(event)")
        }
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
    var inferFromFilenames: Bool = false
    var timeOffsetSeconds: Int?
    var updateFilenameDates: Bool = false

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
        var steps: [PipelineStep] = [.ingest, .tag, .fixTimestamps, .organize]
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
        case .fixTimestamps:
            return !timezone.current.isEmpty
        case .tag, .gyroflow, .archiveSource:
            return true
        }
    }

    func validateTimezone() -> String? {
        if useTimezonePicker { return nil }
        if !enabledSteps.contains(.fixTimestamps) { return nil }
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

    // MARK: - Gyroflow tool availability (UI hint only)

    struct GyroflowToolStatus {
        let ffprobeMissing: Bool
        let gyroflowMissing: Bool
        var anyMissing: Bool { ffprobeMissing || gyroflowMissing }
    }

    /// Pre-flight check: are the external tools needed by the gyroflow step installed?
    /// Checks configured path first (App Store / .dmg), then $PATH (Homebrew).
    static func checkGyroflowTools(gyroflowConfig: GyroflowConfig?) -> GyroflowToolStatus {
        GyroflowToolStatus(
            ffprobeMissing: !isToolInPath("ffprobe"),
            gyroflowMissing: !isGyroflowInstalled(config: gyroflowConfig)
        )
    }

    private static func isToolInPath(_ name: String) -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        process.arguments = [name]
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }

    private static func isGyroflowInstalled(config: GyroflowConfig?) -> Bool {
        if let binary = config?.binary, !binary.isEmpty,
           FileManager.default.isExecutableFile(atPath: binary) {
            return true
        }
        return isToolInPath("gyroflow")
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
            .fixTimestamps: "fix-timestamp",
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
        if enabledSteps.contains(.fixTimestamps) && !timezone.current.isEmpty {
            args += ["--timezone", timezone.current]
        }
        if enabledSteps.contains(.fixTimestamps) && inferFromFilenames {
            args.append("--infer-from-filename")
        }
        if enabledSteps.contains(.fixTimestamps), let offset = timeOffsetSeconds, offset != 0 {
            args += ["--time-offset", String(offset)]
        }
        if updateFilenameDates {
            args.append("--update-filename-dates")
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

    var showInspector: Bool = false
    var showLogOutput: Bool = false

    // Execution state
    var isRunning: Bool = false
    var logOutput: [LogLine] = []
    var currentProcess: Process?
    var diffTableRows: [DiffTableRow] = []
    private var currentDiffRow: DiffTableRow?
    private(set) var liveRow: DiffTableRow?

    /// All completed rows plus the in-progress file for live table display
    var visibleRows: [DiffTableRow] {
        if let live = liveRow {
            return diffTableRows + [live]
        }
        return diffTableRows
    }

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
        liveRow = nil
        showLogOutput = false
    }

    func appendLog(_ line: LogLine) {
        if line.isMachineReadable {
            parseMachineReadableLine(line.text)
            return
        }
        logOutput.append(line)
    }

    private func parseMachineReadableLine(_ text: String) {
        guard let data = text.data(using: .utf8),
              let event = try? JSONDecoder().decode(PipelineEvent.self, from: data)
        else { return }

        switch event {
        case .pipelineFile(let file):
            if var row = currentDiffRow {
                row.pipelineResult = row.pipelineResult ?? "in_progress"
                diffTableRows.append(row)
            }
            currentDiffRow = DiffTableRow(file: file)
            liveRow = currentDiffRow

        case .pipelineResult(_, let result):
            if var row = currentDiffRow {
                row.pipelineResult = result
                diffTableRows.append(row)
                currentDiffRow = nil
                liveRow = nil
            }

        case .tagResult(_, let action, let tagsAdded, _, _):
            currentDiffRow?.tagAction = action
            currentDiffRow?.tagsAdded = tagsAdded.joined(separator: ", ")
            liveRow = currentDiffRow

        case .timestampResult(_, let action, let originalTime, let correctedTime,
                              let source, let timezone, let correctionMode,
                              _, let timeOffsetDisplay):
            currentDiffRow?.timestampAction = action
            currentDiffRow?.originalTime = originalTime
            currentDiffRow?.correctedTime = correctedTime
            currentDiffRow?.timestampSource = source
            currentDiffRow?.timezone = timezone
            currentDiffRow?.correctionMode = correctionMode
            currentDiffRow?.timeOffsetDisplay = timeOffsetDisplay
            liveRow = currentDiffRow

        case .renameResult(_, let renamedTo):
            currentDiffRow?.renamedTo = renamedTo
            liveRow = currentDiffRow

        case .organizeResult(_, let action, let dest):
            currentDiffRow?.organizeAction = action
            currentDiffRow?.dest = dest
            liveRow = currentDiffRow

        case .gyroflowResult:
            liveRow = currentDiffRow

        case .stageComplete(let stage):
            currentDiffRow?.markStageComplete(stage)
            liveRow = currentDiffRow
        }
    }

    func cancelRunning() {
        currentProcess?.terminate()
        currentProcess = nil
        isRunning = false
    }
}
