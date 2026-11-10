import Foundation
import Observation

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
    /// The source as last chosen — the profile's own, a folder browsed to, or a
    /// typed path once it is entered — not each keystroke on the way to it.
    /// Whatever reads the source keys on this, so a half-typed path is never walked.
    private(set) var chosenSource: String
    /// Whether the chosen source holds files with a timestamp in their names;
    /// false until it has been read.
    private(set) var sourceHasTimestampedNames = false
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

    var timezoneConflictType: TimezoneConflictKind?
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

    var protectedSourceFiles: [String] = []
    var showProtectedSources: Bool = false
    var unlockProtected: Bool = false

    var cameraMismatch: CameraMismatch?
    var showCameraMismatch: Bool = false
    var allowCameraMismatch: Bool = false

    /// Whether the run a conflict alert asks about was an apply. A finished
    /// apply has dropped back to preview mode before the user answers, so the
    /// answer needs this to re-run what was actually refused.
    private var conflictedRunWasApply = false

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
    /// step could only ever skip files, so it is not offered at all. An install
    /// found while the session is open offers the step as a new session would:
    /// on, if the profile asks for it. A re-check that finds the same install
    /// leaves the user's choice alone.
    var gyroflowAvailable: Bool {
        didSet {
            if !gyroflowAvailable {
                enabledSteps.remove(.gyroflow)
            } else if !oldValue, availableSteps.contains(.gyroflow), Self.isOnByDefault(.gyroflow) {
                enabledSteps.insert(.gyroflow)
            }
        }
    }

    init(profile: MediaProfile? = nil, profileName: String = "", gyroflowAvailable: Bool = false) {
        self.profileName = profileName
        self.workingProfile = profile ?? MediaProfile()
        self.sourceDir = Dirtyable(profile?.sourceDir ?? "")
        self.chosenSource = profile?.sourceDir ?? ""
        self.readyDir = Dirtyable(profile?.readyDir ?? "")
        self.tags = Dirtyable(profile?.tags)
        self.timezone = Dirtyable("")
        self.gyroflowAvailable = gyroflowAvailable
        let availableSteps = Self.computeAvailableSteps(
            profile: profile, gyroflowAvailable: gyroflowAvailable
        )
        self.enabledSteps = Set(availableSteps.filter(Self.isOnByDefault))
    }

    /// Whether a step the session offers starts switched on. Archiving moves the
    /// user's source folder, so it is only ever opted into.
    private static func isOnByDefault(_ step: PipelineStep) -> Bool {
        step != .archiveSource
    }

    var availableSteps: [PipelineStep] {
        Self.computeAvailableSteps(profile: workingProfile, gyroflowAvailable: gyroflowAvailable)
    }

    func toggle(_ step: PipelineStep) {
        guard !step.isAlwaysOn else { return }
        if enabledSteps.contains(step) {
            enabledSteps.remove(step)
        } else {
            enabledSteps.insert(step)
        }
    }

    func noteConflict() {
        conflictedRunWasApply = applyMode
    }

    /// The refused apply had already passed the dry-run question, so its
    /// re-run is not asked again.
    private func resumeConflictedRun() {
        guard conflictedRunWasApply else { return }
        applyMode = true
        applyWithoutDryRun = true
    }

    /// Record the user's answer to the conflict the pipeline just refused on,
    /// so the next run carries the override flag that unblocks it.
    func grantTimezoneAssent() {
        if timezoneConflictType == .mixedTimezones {
            allowMixedTimezones = true
        } else {
            forceTimezone = true
        }
        showTimezoneConflict = false
        resumeConflictedRun()
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

    /// Record the user's answer, so the re-run imports the files shot on
    /// another camera, their camera fields left as the camera wrote them.
    func grantCameraMismatchAssent() {
        allowCameraMismatch = true
        showCameraMismatch = false
        resumeConflictedRun()
    }

    /// Record the user's answer, so the re-run carries the flag that imports
    /// the protected files as unlocked copies.
    func grantUnlockProtectedAssent() {
        unlockProtected = true
        showProtectedSources = false
        resumeConflictedRun()
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

    func chooseSource() {
        guard chosenSource != sourceDir.current else { return }
        chosenSource = sourceDir.current
        sourceHasTimestampedNames = false
    }

    /// What reading the chosen source found. Filenames cannot be the timestamp
    /// source for files whose names carry none.
    func noteTimestampedNames(_ found: Bool, in source: String) {
        guard source == chosenSource else { return }
        sourceHasTimestampedNames = found
        if !found {
            inferFromFilenames = false
        }
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
        resetApplyModeAfterRun()
    }

    func noteRunCancelled() {
        if runningDryRunArgs != nil {
            lastDryRunArgs = nil
        }
        runningDryRunArgs = nil
        resetApplyModeAfterRun()
    }

    /// An apply that just finished or was cancelled leaves nothing previewed
    /// for the next one, so the stale-dry-run assent it may have needed must
    /// not carry over — the workflow defaults back to the safe preview.
    private func resetApplyModeAfterRun() {
        guard applyMode else { return }
        applyMode = false
        applyWithoutDryRun = false
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
        protectedSourceFiles = []
        showProtectedSources = false
        unlockProtected = false
        cameraMismatch = nil
        showCameraMismatch = false
        allowCameraMismatch = false
        conflictedRunWasApply = false
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
    static let unlockProtectedFlag = "--unlock-protected"
    static let allowCameraMismatchFlag = "--allow-camera-mismatch"
    static let applyFlag = "--apply"

    /// What the run carries because of an answer given for one click, rather
    /// than a setting the user chose — the same state `clearRunAssent()` drops.
    static let assentFlags = [
        forceTimezoneFlag, allowMixedTimezonesFlag, overwriteFlag, unlockProtectedFlag,
        allowCameraMismatchFlag, applyFlag,
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

        let tasks = availableSteps
            .filter { enabledSteps.contains($0) }
            .compactMap(\.taskToken)
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
        if unlockProtected {
            args.append(Self.unlockProtectedFlag)
        }
        if allowCameraMismatch {
            args.append(Self.allowCameraMismatchFlag)
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

    // MARK: - What the form previews

    /// What the timezone question says about the conflict the pipeline refused on.
    var timezoneConflictMessage: String {
        guard let fileTimezones = timezoneConflictFileTimezones else { return "" }
        switch timezoneConflictType {
        case .mixedTimezones:
            let groups = fileTimezones
                .map { zone, files in Strings.Workflow.mixedTimezoneGroup(zone: zone, count: files.count) }
                .sorted()
                .joined(separator: "\n")
            return Strings.Workflow.mixedTimezonesMessage(groups: groups)
        case .providedMismatch, nil:
            let existing = fileTimezones.keys.sorted().joined(separator: ", ")
            return Strings.Workflow.providedMismatchMessage(
                provided: timezoneConflictProvidedTz ?? "", existing: existing)
        }
    }

    /// One line under the Fix Timestamps step saying what the run will do to
    /// each file's time, or nil when the step is off or changes nothing yet.
    var fixTimestampPreview: String? {
        guard enabledSteps.contains(.fixTimestamps) else { return nil }

        var parts: [String] = []
        if inferFromFilenames {
            if let option = timezoneOption {
                parts.append(option.offsets.count > 1
                    ? Strings.Workflow.fixTimestampSourceFilenamesZoneMultiHint(city: option.city)
                    : Strings.Workflow.fixTimestampSourceFilenamesZoneHint(city: option.city, offsetLabel: option.offsetLabel))
            } else {
                parts.append(Strings.Workflow.fixTimestampSourceFilenamesHint)
            }
        }
        if let offset = timeOffsetSeconds, offset != 0 {
            let sign = offset > 0 ? "+" : ""
            parts.append(Strings.Workflow.fixTimestampShiftHint(sign: sign, offset: offset))
        }
        if let option = timezoneOption, !inferFromFilenames {
            parts.append(option.offsets.count > 1
                ? Strings.Workflow.fixTimestampZoneMultiHint(city: option.city)
                : Strings.Workflow.fixTimestampZoneHint(city: option.city, offsetLabel: option.offsetLabel))
        }
        if updateFilenameDates {
            parts.append(Strings.Workflow.fixTimestampRenameHint)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// Where organized files land, laid out as the pipeline lays them out: the
    /// profile's `folder_template` when it has one, otherwise year / [group /]
    /// date. Date parts show as their placeholders (YYYY, MM, …).
    var destinationPreview: String {
        let template: String
        if let folderTemplate = workingProfile.folderTemplate, !folderTemplate.isEmpty {
            template = group.isEmpty
                ? folderTemplate
                : folderTemplate.replacingOccurrences(of: "{{GROUP}}", with: group)
        } else if !group.isEmpty {
            template = "{{YYYY}}/\(group)/{{YYYY}}-{{MM}}-{{DD}}"
        } else {
            template = "{{YYYY}}/{{YYYY}}-{{MM}}-{{DD}}"
        }
        var relative = template
        for token in ["YYYY-MM-DD", "YYYY", "MMM", "MM", "DD"] {
            relative = relative.replacingOccurrences(of: "{{\(token)}}", with: token)
        }
        relative = relative.replacingOccurrences(of: "//", with: "/")
        while relative.hasSuffix("/") {
            relative.removeLast()
        }
        return readyDir.current + "/" + relative
    }
}
