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
    /// Text without the ANSI colour codes the scripts write for terminal use.
    /// Computed once here: the log view renders every line exactly once, and a
    /// transcript of thousands of lines must never be re-stripped per update.
    let strippedText: String

    enum Stream {
        case stdout, stderr
    }

    init(text: String, stream: Stream) {
        self.text = text
        self.stream = stream
        self.strippedText = text
            .replacingOccurrences(of: "\u{1B}\\[[0-9;]*m", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
    }

    var isMachineReadable: Bool {
        text.hasPrefix("{")
    }
}

/// JSONL event types emitted by media-pipeline.py on stdout.
enum PipelineEvent: Decodable {
    case pipelineFile(file: String, sourcePath: String?)
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
    case pipelineSummary(PipelineSummary)
    case timezoneConflict(conflictType: String, providedTz: String?,
                          fileTimezones: [String: [String]])
    case organizeConflict(count: Int, files: [String])
    case pipelineError(message: String)

    private enum CodingKeys: String, CodingKey {
        case event, file, stage, action
        case sourcePath = "source_path"
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
        case count, files
        case processed, succeeded, changed, failed, mode
        case failedFiles = "failed_files"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let event = try container.decode(String.self, forKey: .event)

        switch event {
        case "pipeline_file":
            self = .pipelineFile(
                file: try container.decode(String.self, forKey: .file),
                sourcePath: try container.decodeIfPresent(String.self, forKey: .sourcePath))
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
        case "pipeline_summary":
            let modeToken = try container.decode(String.self, forKey: .mode)
            guard let mode = PipelineSummary.Mode(rawValue: modeToken) else {
                throw DecodingError.dataCorruptedError(
                    forKey: .mode, in: container,
                    debugDescription: "Unknown pipeline_summary mode: \(modeToken)")
            }
            self = .pipelineSummary(PipelineSummary(
                processed: try container.decode(Int.self, forKey: .processed),
                succeeded: try container.decode(Int.self, forKey: .succeeded),
                changed: try container.decode(Int.self, forKey: .changed),
                failed: try container.decode(Int.self, forKey: .failed),
                failedFiles: try container.decode([String].self, forKey: .failedFiles),
                mode: mode))
        case "timezone_conflict":
            self = .timezoneConflict(
                conflictType: try container.decode(String.self, forKey: .conflictType),
                providedTz: try container.decodeIfPresent(String.self, forKey: .providedTz),
                fileTimezones: try container.decode([String: [String]].self, forKey: .fileTimezones))
        case "organize_conflict":
            self = .organizeConflict(
                count: try container.decode(Int.self, forKey: .count),
                files: try container.decode([String].self, forKey: .files))
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

    /// What the last run reported it could not move: a different file already
    /// occupies those destinations. The report outlives the run that made it,
    /// because it is the preview the user reads before deciding to apply.
    var organizeConflictCount: Int = 0
    var organizeConflictFiles: [String] = []
    var showOverwriteConflict: Bool = false
    var overwriteDestination: Bool = false

    /// Where the archived source folder lands and what it is called. Both are
    /// overrides on top of archiving in place under "<source> - copied <date>",
    /// which is what the folder does when the user changes neither.
    var archiveDestinationOverride: String?
    var renameSourceDir: Bool = true
    var archivedNameOverride: String?

    /// Why the apply about to start was never previewed, which is the whole of
    /// what the question asks.
    enum DryRunStaleReason {
        case noDryRun
        case settingsChanged
    }

    /// The settings the last completed dry run previewed. A run that was
    /// cancelled never becomes one: it stopped partway through the files, so
    /// the table it left is not a preview of the whole batch.
    private var lastDryRunArgs: [String]?
    private var runningDryRunArgs: [String]?

    var dryRunStaleReason: DryRunStaleReason?
    var showDryRunStale: Bool = false
    var applyWithoutDryRun: Bool = false

    var enabledSteps: Set<PipelineStep> = []

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

    /// Whether the run has to stop and ask first: applying over the files the
    /// last run reported blocked replaces them for good, so it needs an answer.
    /// Returns true when the question was raised and the run must not start.
    func requestOverwriteAssentIfNeeded() -> Bool {
        guard applyMode, !overwriteDestination, organizeConflictCount > 0 else { return false }
        showOverwriteConflict = true
        return true
    }

    /// Record the user's answer, so the re-run carries the flag that replaces
    /// the files already at the destination.
    func grantOverwriteAssent() {
        overwriteDestination = true
        showOverwriteConflict = false
    }

    /// The settings a run would carry, with the answers given for this click
    /// taken out: an override the user just granted is not a setting they
    /// changed, so it never makes the preview they read look stale.
    func comparableArgs() -> [String] {
        buildPipelineArgs().args.filter { !Self.assentFlags.contains($0) }
    }

    /// Whether the apply has to stop and ask first: an apply moves and replaces
    /// real files, so the only thing that makes it safe is a preview of this
    /// exact run. Returns true when the question was raised and the run must
    /// not start.
    func requestDryRunAssentIfNeeded() -> Bool {
        guard applyMode, !applyWithoutDryRun else { return false }
        guard let previewed = lastDryRunArgs else {
            dryRunStaleReason = .noDryRun
            showDryRunStale = true
            return true
        }
        guard previewed != comparableArgs() else { return false }
        dryRunStaleReason = .settingsChanged
        showDryRunStale = true
        return true
    }

    /// Record the user's answer, so the apply they insisted on goes ahead.
    func grantDryRunStaleAssent() {
        applyWithoutDryRun = true
        showDryRunStale = false
    }

    /// The offered alternative: preview these settings instead of applying them.
    func startDryRunInstead() {
        applyMode = false
        showDryRunStale = false
    }

    /// A dry run counts as the preview only once it has been through every
    /// file, so what it previewed is held until it finishes.
    func noteRunStarted() {
        runningDryRunArgs = applyMode ? nil : comparableArgs()
    }

    func noteRunFinished() {
        if let previewed = runningDryRunArgs {
            lastDryRunArgs = previewed
        }
        runningDryRunArgs = nil
    }

    func noteRunCancelled() {
        runningDryRunArgs = nil
    }

    /// Assent covers the run it was given for. A run the user starts themselves
    /// begins without it, so a later batch is never relabelled or replaced unasked.
    func clearRunAssent() {
        forceTimezone = false
        allowMixedTimezones = false
        showTimezoneConflict = false
        timezoneConflictType = nil
        timezoneConflictProvidedTz = nil
        timezoneConflictFileTimezones = nil
        overwriteDestination = false
        showOverwriteConflict = false
        applyWithoutDryRun = false
        showDryRunStale = false
        dryRunStaleReason = nil
    }

    /// The conflict report describes the rows of the run that produced it, so it
    /// is discarded with them rather than carried into the next run's table.
    func clearConflictReport() {
        organizeConflictCount = 0
        organizeConflictFiles = []
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
        case .archiveSource:
            return validateArchiveSource() == nil
        case .tag, .gyroflow:
            return true
        }
    }

    /// The source folder as the archive step will act on it: an empty or
    /// trailing-slashed path is not one, and Ingest already reports a missing one.
    private var sourceURL: URL? {
        guard !sourceDir.current.isEmpty else { return nil }
        return URL(fileURLWithPath: sourceDir.current).standardizedFileURL
    }

    var sourceDirName: String { sourceURL?.lastPathComponent ?? "" }

    var defaultArchiveDestination: String {
        sourceURL?.deletingLastPathComponent().path ?? ""
    }

    var defaultArchivedName: String {
        guard let sourceURL else { return "" }
        return Strings.Workflow.archivedNameDefault(
            source: sourceURL.lastPathComponent, date: Self.archivedNameDate(Date())
        )
    }

    static func archivedNameDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    var archiveDestination: String {
        get { archiveDestinationOverride ?? defaultArchiveDestination }
        set { archiveDestinationOverride = newValue }
    }

    /// The name the folder is left under. Rename off keeps the name it has, so
    /// the step is a plain move into whatever destination was chosen.
    var archivedName: String {
        get { renameSourceDir ? (archivedNameOverride ?? defaultArchivedName) : sourceDirName }
        set { archivedNameOverride = newValue }
    }

    var archivedPath: String {
        URL(fileURLWithPath: archiveDestination)
            .appendingPathComponent(archivedName)
            .standardizedFileURL.path
    }

    /// An archive that resolves back to the source path moves nothing and
    /// renames nothing, so it is not a step that can be run.
    func validateArchiveSource() -> String? {
        if !enabledSteps.contains(.archiveSource) { return nil }
        guard let sourceURL else { return nil }
        if let error = validateDirectory(archiveDestination) { return error }
        if archivedPath == sourceURL.path { return Strings.Workflow.archiveNoChange }
        return nil
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

    static let forceTimezoneFlag = "--force-timezone"
    static let allowMixedTimezonesFlag = "--allow-mixed-timezones"
    static let overwriteFlag = "--overwrite"
    static let applyFlag = "--apply"

    /// What the run carries because of an answer given for one click, rather
    /// than a setting the user chose — the same state `clearRunAssent()` drops.
    private static let assentFlags = [
        forceTimezoneFlag, allowMixedTimezonesFlag, overwriteFlag, applyFlag,
    ]

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

        if enabledSteps.contains(.archiveSource) {
            args += ["--archive-destination", archiveDestination]
            args += ["--archived-name", archivedName]
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
            args.append(Self.forceTimezoneFlag)
        }
        if allowMixedTimezones {
            args.append(Self.allowMixedTimezonesFlag)
        }
        if overwriteDestination {
            args.append(Self.overwriteFlag)
        }
        if applyMode {
            args.append(Self.applyFlag)
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

    /// The log's live view, owned here rather than by the panel: the inspector shows the
    /// log behind a conditional, and a view rebuilt on every toggle comes back with the
    /// transcript to re-render and the user's scroll position lost.
    let logViewHolder = LogViewHolder()

    /// Message shown when a run was refused because the Python interpreter the
    /// scripts resolve cannot be invoked.
    var pythonRuntimeAlert: String?

    // Execution state
    var isRunning: Bool = false
    var logOutput: [LogLine] = []
    var currentProcess: ScriptProcess?
    /// The task draining the process's output into the log. Cancelling the run must
    /// cancel this too: the pipeline can be far ahead of the UI, and terminating the
    /// process alone leaves every buffered line still to be appended.
    var currentRunTask: Task<Void, Never>?
    var diffTableRows: [DiffTableRow] = []
    /// What the last run reported when it reached the end of the batch. A
    /// cancelled run never produces one: the pipeline is killed before it reports.
    private(set) var runSummary: PipelineSummary?
    var showRunSummary: Bool = false
    private(set) var currentDiffRow: DiffTableRow?
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
        runSummary = nil
        showRunSummary = false
        workflowSession.clearConflictReport()
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
        case .pipelineFile(let file, let sourcePath):
            if var row = currentDiffRow {
                row.pipelineResult = row.pipelineResult ?? "in_progress"
                diffTableRows.append(row)
            }
            var started = DiffTableRow(file: file)
            started.sourcePath = sourcePath
            currentDiffRow = started
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

        case .organizeConflict(let count, let files):
            workflowSession.organizeConflictCount = count
            workflowSession.organizeConflictFiles = files

        case .pipelineSummary(let summary):
            runSummary = summary

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

    /// The run reached the end of the pipeline's output. Its counterpart is
    /// cancelRunning: only a run that finished has an outcome to show, so the
    /// popup is raised from the summary the pipeline reported, or not at all.
    func finishRun() {
        workflowSession.noteRunFinished()
        isRunning = false
        currentProcess = nil
        currentRunTask = nil
        showRunSummary = runSummary != nil
    }

    func cancelRunning() {
        workflowSession.noteRunCancelled()
        currentRunTask?.cancel()
        currentRunTask = nil
        // The whole group, not just the script: the pipeline's jetlag-metadata and
        // exiftool children would otherwise be re-parented to launchd and live on.
        currentProcess?.terminateGroup()
        currentProcess = nil
        isRunning = false
        // The drain task is cancelled above before the pipeline's own "Interrupted by
        // user" line can arrive, so that line never reaches the log. This is the app's
        // own line, not parsed from the pipeline's output.
        logOutput.append(LogLine(text: Strings.LogOutput.cancelled, stream: .stderr))
        liveRow = nil
        currentDiffRow = nil
    }
}
