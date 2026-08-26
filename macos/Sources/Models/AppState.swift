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

    /// Text without the ANSI colour codes the scripts write for terminal use.
    var strippedText: String {
        text
            .replacingOccurrences(of: "\u{1B}\\[[0-9;]*m", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
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
                         timeOffsetDisplay: String?,
                         error: String?,
                         originalEpoch: Double?,
                         correctedEpoch: Double?,
                         requiresForceTimezone: Bool,
                         staleFields: [String])
    case renameResult(file: String, renamedTo: String)
    case organizeResult(file: String, action: String, dest: String, reason: String?)
    case gyroflowResult(file: String, action: String, gyroflowPath: String,
                        error: String?)
    case pipelineResult(file: String, result: String)
    case timezoneConflict(conflictType: String, providedTz: String?,
                          fileTimezones: [String: [String]])
    case pipelineError(message: String)

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
        case originalEpoch = "original_epoch"
        case correctedEpoch = "corrected_epoch"
        case requiresForceTimezone = "requires_force_timezone"
        case staleFields = "stale_fields"
        case renamedTo = "renamed_to"
        case dest, reason
        case gyroflowPath = "gyroflow_path"
        case error, result, message
        case conflictType = "conflict_type"
        case providedTz = "provided_tz"
        case fileTimezones = "file_timezones"
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
                timeOffsetDisplay: try container.decodeIfPresent(String.self, forKey: .timeOffsetDisplay),
                error: try container.decodeIfPresent(String.self, forKey: .error),
                originalEpoch: try container.decodeIfPresent(Double.self, forKey: .originalEpoch),
                correctedEpoch: try container.decodeIfPresent(Double.self, forKey: .correctedEpoch),
                requiresForceTimezone: try container.decodeIfPresent(Bool.self, forKey: .requiresForceTimezone) ?? false,
                staleFields: try container.decodeIfPresent([String].self, forKey: .staleFields) ?? [])
        case "rename_result":
            self = .renameResult(
                file: try container.decode(String.self, forKey: .file),
                renamedTo: try container.decode(String.self, forKey: .renamedTo))
        case "organize_result":
            self = .organizeResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                dest: try container.decode(String.self, forKey: .dest),
                reason: try container.decodeIfPresent(String.self, forKey: .reason))
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
        case "timezone_conflict":
            self = .timezoneConflict(
                conflictType: try container.decode(String.self, forKey: .conflictType),
                providedTz: try container.decodeIfPresent(String.self, forKey: .providedTz),
                fileTimezones: try container.decode([String: [String]].self, forKey: .fileTimezones))
        case "pipeline_error":
            self = .pipelineError(
                message: try container.decode(String.self, forKey: .message))
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

    /// A new source folder is a new batch of footage, so any zone declared for
    /// the previous one is dropped: the declaration has to be made against the
    /// files it will label, never inherited from an earlier, unrelated import.
    var sourceDir: Dirtyable<String> {
        didSet {
            guard sourceDir.current != oldValue.current else { return }
            timezone = Dirtyable("")
        }
    }
    var readyDir: Dirtyable<String>
    var tags: Dirtyable<[String]?>
    var timezone: Dirtyable<String>

    var group: String = ""
    var copyCompanionFiles: Bool = false
    var sourceAction: SourceAction = .archive
    var applyMode: Bool = false
    var inferFromFilenames: Bool = false
    var timeOffsetSeconds: Int?
    var updateFilenameDates: Bool = false
    var forceTimezone: Bool = false
    var allowMixedTimezones: Bool = false

    var timezoneConflictType: String?
    var timezoneConflictProvidedTz: String?
    var timezoneConflictFileTimezones: [String: [String]]?
    var showTimezoneConflict: Bool = false

    var enabledSteps: Set<PipelineStep> = [] {
        didSet {
            if !enabledSteps.contains(.archiveSource) {
                sourceAction = .archive
            }
        }
    }

    /// Whether a Gyroflow install was found on this machine. Without one the
    /// step could only ever skip files, so it is not offered at all.
    var gyroflowAvailable: Bool {
        didSet {
            if !gyroflowAvailable {
                enabledSteps.remove(.gyroflow)
            }
        }
    }

    init(profile: MediaProfile? = nil, profileName: String = "", gyroflowAvailable: Bool = false) {
        self.profileName = profileName
        self.workingProfile = profile ?? MediaProfile()
        self.sourceDir = Dirtyable(profile?.sourceDir ?? "")
        self.readyDir = Dirtyable(profile?.readyDir ?? "")
        self.tags = Dirtyable(profile?.tags)
        self.timezone = Dirtyable("")
        self.gyroflowAvailable = gyroflowAvailable
        let availableSteps = Self.computeAvailableSteps(
            profile: profile, gyroflowAvailable: gyroflowAvailable
        )
        self.enabledSteps = Set(availableSteps.filter { $0 != .archiveSource })
    }

    var availableSteps: [PipelineStep] {
        Self.computeAvailableSteps(profile: workingProfile, gyroflowAvailable: gyroflowAvailable)
    }

    /// Record the user's answer to the conflict the pipeline just refused on,
    /// so the next run carries the override flag that unblocks it.
    func grantTimezoneAssent() {
        if timezoneConflictType == "mixed_timezones" {
            allowMixedTimezones = true
        } else {
            forceTimezone = true
        }
        showTimezoneConflict = false
    }

    /// Assent covers the run it was given for. A run the user starts themselves
    /// begins without it, so a later batch is never relabelled unasked.
    func clearTimezoneAssent() {
        forceTimezone = false
        allowMixedTimezones = false
        showTimezoneConflict = false
        timezoneConflictType = nil
        timezoneConflictProvidedTz = nil
        timezoneConflictFileTimezones = nil
    }

    private static func computeAvailableSteps(
        profile: MediaProfile?, gyroflowAvailable: Bool
    ) -> [PipelineStep] {
        guard let profile else { return [] }
        var steps: [PipelineStep] = [.ingest, .tag, .fixTimestamps]
        if gyroflowAvailable && profile.gyroflowEnabled == true {
            steps.append(.gyroflow)
        }
        steps.append(contentsOf: [.organize, .archiveSource])
        return steps
    }

    func isStepReady(_ step: PipelineStep) -> Bool {
        switch step {
        case .ingest:
            return validateDirectory(sourceDir.current) == nil
        case .organize:
            return validateDirectory(readyDir.current) == nil
        case .fixTimestamps:
            return validateTimezone() == nil
        case .tag, .gyroflow, .archiveSource:
            return true
        }
    }

    var timezoneOption: TimezoneOption? {
        TimezoneCatalog.option(timezone.current)
    }

    func validateTimezone() -> String? {
        if !enabledSteps.contains(.fixTimestamps) { return nil }
        if timezone.current.isEmpty { return Strings.Workflow.timezoneRequired }
        if timezoneOption == nil { return Strings.Workflow.timezoneUnknown }
        return nil
    }

    var allStepsReady: Bool {
        let active = availableSteps.filter { $0.isAlwaysOn || enabledSteps.contains($0) }
        return active.allSatisfy { isStepReady($0) }
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
        if enabledSteps.contains(.fixTimestamps), let option = timezoneOption {
            args += ["--timezone", option.id]
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
        if forceTimezone {
            args.append("--force-timezone")
        }
        if allowMixedTimezones {
            args.append("--allow-mixed-timezones")
        }
        if applyMode {
            args.append("--apply")
        }

        if enabledSteps.contains(.gyroflow), let settings = workingProfile.gyroflowSettings {
            var stabilization: [String: Any] = [:]
            if let maxZoom = settings.maxZoom {
                stabilization["max_zoom"] = maxZoom
            }
            if let window = settings.adaptiveZoomWindow {
                stabilization["adaptive_zoom_window"] = window
            }
            if let method = settings.adaptiveZoomMethod {
                stabilization["adaptive_zoom_method"] = method
            }

            if !stabilization.isEmpty {
                let preset: [String: Any] = ["stabilization": stabilization]
                if let data = try? JSONSerialization.data(withJSONObject: preset),
                   let json = String(data: data, encoding: .utf8) {
                    args += ["--gyroflow-preset", json]
                }
            }
        }

        return (script: "media-pipeline.sh", args: args)
    }
}

@Observable
final class AppState {
    var selectedTab: SidebarTab = .workflow {
        didSet {
            if selectedTab != .workflow {
                clearLog()
                showLogOutput = false
                showInspector = false
            }
        }
    }

    let scriptsDirectory: String

    /// The user-owned profiles file, and the bundled copy it is seeded from.
    let profilesLocation: ProfilesLocation

    /// Settings override pointing the app at another profiles file — how a
    /// development build is aimed at the repo's checked-in copy.
    var profilesFilePath: String {
        didSet { UserDefaults.standard.set(profilesFilePath, forKey: "profilesFilePath") }
    }

    var profilesConfig: ProfilesConfig?
    var profileLoadError: ProfileLoadError?

    var sortedProfileNames: [String] {
        profilesConfig?.profiles.keys.sorted() ?? []
    }

    var workflowSession = WorkflowSession()

    /// Presence of the optional Gyroflow install, refreshed on launch and after
    /// an install. Every gyroflow feature in the app is gated on this.
    var gyroflowStatus: GyroflowStatus = .notInstalled {
        didSet { workflowSession.gyroflowAvailable = gyroflowStatus.isInstalled }
    }
    var isInstallingGyroflow: Bool = false
    var gyroflowInstallProgress: String?

    var showInspector: Bool = false
    var showLogOutput: Bool = false

    /// Message shown when a run was refused because the Python interpreter the
    /// scripts resolve cannot be invoked.
    var pythonRuntimeAlert: String?

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

    /// The most recent line of pipeline progress, for the stretch between starting
    /// a run and the first file appearing in the table.
    var latestStatusLine: String? {
        logOutput.last { !$0.strippedText.isEmpty }?.strippedText
    }

    init() {
        let scriptsDirectory = (Bundle.main.resourcePath! as NSString)
            .appendingPathComponent("scripts")
        self.scriptsDirectory = scriptsDirectory
        self.profilesLocation = ProfilesLocation.userDomain(scriptsDirectory: scriptsDirectory)
        self.profilesFilePath = UserDefaults.standard.string(forKey: "profilesFilePath") ?? ""
    }

    var resolvedProfilesPath: String {
        profilesFilePath.isEmpty ? profilesLocation.path : profilesFilePath
    }

    /// Seed the user's profiles file from the bundled defaults when it is not
    /// there yet, then load it. An override points somewhere the user chose, so
    /// nothing is ever written there on its behalf.
    func loadProfiles() {
        if profilesFilePath.isEmpty {
            do {
                try profilesLocation.seedIfNeeded()
            } catch {
                profilesConfig = nil
                profileLoadError = ProfileLoadError(
                    message: Strings.Errors.profilesSeedFailed,
                    filePath: profilesLocation.path,
                    detail: error.localizedDescription
                )
                return
            }
        }
        do {
            profilesConfig = try ProfileService.load(from: resolvedProfilesPath).normalized()
            profileLoadError = nil
        } catch {
            profilesConfig = nil
            profileLoadError = error
        }
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
                              _, let timeOffsetDisplay, let error,
                              let originalEpoch, let correctedEpoch,
                              let requiresForceTimezone, let staleFields):
            currentDiffRow?.timestampAction = action
            currentDiffRow?.originalTime = originalTime
            currentDiffRow?.correctedTime = correctedTime
            currentDiffRow?.timestampSource = TimestampSource(token: source)
            currentDiffRow?.timezone = timezone
            currentDiffRow?.correctionMode = correctionMode
            currentDiffRow?.timeOffsetDisplay = timeOffsetDisplay
            currentDiffRow?.timestampError = error
            currentDiffRow?.originalEpoch = originalEpoch
            currentDiffRow?.correctedEpoch = correctedEpoch
            currentDiffRow?.requiresForceTimezone = requiresForceTimezone
            currentDiffRow?.staleFields = staleFields
            liveRow = currentDiffRow

        case .renameResult(_, let renamedTo):
            currentDiffRow?.renamedTo = renamedTo
            liveRow = currentDiffRow

        case .organizeResult(_, let action, let dest, let reason):
            currentDiffRow?.organizeAction = action
            currentDiffRow?.dest = dest
            currentDiffRow?.organizeReason = reason
            liveRow = currentDiffRow

        case .gyroflowResult:
            liveRow = currentDiffRow

        case .stageComplete(let stage):
            currentDiffRow?.markStageComplete(stage)
            liveRow = currentDiffRow

        case .timezoneConflict(let conflictType, let providedTz, let fileTimezones):
            workflowSession.timezoneConflictType = conflictType
            workflowSession.timezoneConflictProvidedTz = providedTz
            workflowSession.timezoneConflictFileTimezones = fileTimezones
            // A dry run previews a provided-vs-embedded mismatch instead of
            // refusing it, so the conflict is recorded as data and the flagged
            // rows speak for themselves. Only a run the pipeline actually
            // refuses — an apply, or a mixed-zone batch in either mode — asks
            // the user to confirm.
            workflowSession.showTimezoneConflict =
                conflictType == "mixed_timezones" || workflowSession.applyMode

        case .pipelineError(let message):
            logOutput.append(LogLine(text: "ERROR: \(message)", stream: .stderr))
        }
    }

    /// Ask download-gyroflow.sh where Gyroflow is, without downloading anything.
    func refreshGyroflowStatus() async {
        gyroflowStatus = await runGyroflowScript(args: ["--check"])
    }

    /// Download and install Gyroflow.app into Application Support.
    func installGyroflow() async {
        isInstallingGyroflow = true
        gyroflowInstallProgress = nil
        gyroflowStatus = await runGyroflowScript(args: [])
        isInstallingGyroflow = false
        gyroflowInstallProgress = nil
    }

    private func runGyroflowScript(args: [String]) async -> GyroflowStatus {
        let (process, stream) = ScriptRunner.run(
            script: "tools/download-gyroflow.sh",
            args: args,
            workingDir: scriptsDirectory,
            profilesPath: resolvedProfilesPath
        )
        var presenceData: [String] = []
        for await line in stream {
            switch line.stream {
            case .stdout:
                presenceData.append(line.text)
            case .stderr:
                gyroflowInstallProgress = line.strippedText
            }
        }
        process.waitUntilExit()
        return GyroflowStatus.parse(presenceData.joined(separator: "\n"))
    }

    /// Gate the pipeline on the Python interpreter before launching it. The
    /// scripts run on the Python macOS ships, and on a Mac with neither Xcode
    /// nor the Command Line Tools `/usr/bin/python3` is a shim that opens the
    /// developer-tools install dialog — so the run is refused with a message
    /// naming what to install rather than started.
    func canRunPipeline(check: PythonRuntimeCheck = .system) -> Bool {
        switch check.status {
        case .ready:
            pythonRuntimeAlert = nil
            return true
        case .commandLineToolsMissing:
            pythonRuntimeAlert = Strings.Errors.commandLineToolsMissing
            return false
        }
    }

    func cancelRunning() {
        currentProcess?.terminate()
        currentProcess = nil
        isRunning = false
    }
}
