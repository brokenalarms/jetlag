import Foundation
import SwiftUI

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

    /// Starts every script the app runs.
    let launcher: any ScriptLaunching

    /// The free-tier limit a run is checked against.
    let licenseStore: LicenseStore

    /// Set when a run was refused for having more files than the free tier
    /// allows; the upgrade sheet shows while it is.
    var upgradePrompt: UpgradePrompt?

    struct UpgradePrompt: Identifiable {
        let fileCount: Int
        var id: Int { fileCount }
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
    /// The last run's events, folded into the table's rows and its summary.
    var transcript = RunTranscript()
    var showRunSummary: Bool = false

    var diffTableRows: [DiffTableRow] { transcript.rows }
    var liveRow: DiffTableRow? { transcript.liveRow }
    var runSummary: PipelineSummary? { transcript.summary }
    var emptySource: EmptySource? { transcript.emptySource }
    /// All completed rows plus the in-progress file for live table display
    var visibleRows: [DiffTableRow] { transcript.visibleRows }

    /// The most recent line of pipeline progress, for the stretch between starting
    /// a run and the first file appearing in the table.
    var latestStatusLine: String? {
        logOutput.last { !$0.strippedText.isEmpty }?.strippedText
    }

    /// Tests pass a location in a temporary directory: they run inside the app,
    /// so the default is the user's own profiles file. They pass a launcher that
    /// replays recorded output, and a license store on defaults of their own.
    init(
        profilesLocation: ProfilesLocation? = nil,
        launcher: (any ScriptLaunching)? = nil,
        licenseStore: LicenseStore = .shared
    ) {
        let scriptsDirectory = (Bundle.main.resourcePath! as NSString)
            .appendingPathComponent("scripts")
        self.scriptsDirectory = scriptsDirectory
        let location = profilesLocation
            ?? ProfilesLocation.userDomain(scriptsDirectory: scriptsDirectory)
        self.profilesLocation = location
        self.launcher = launcher
            ?? LiveScriptLauncher(scriptsDirectory: scriptsDirectory, profilesPath: location.path)
        self.licenseStore = licenseStore
    }

    /// Seed the user's profiles file from the bundled defaults when it is not
    /// there yet, then load it.
    func loadProfiles() {
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
        do {
            let selected = workflowSession.profileName
            let previous = settings(ofProfile: selected)
            profilesConfig = try ProfileService.load(from: profilesLocation.path)
            profileLoadError = nil
            // A workflow whose profile was changed or removed in the file follows
            // it; one whose profile is as it was keeps every choice made for it.
            if !selected.isEmpty, settings(ofProfile: selected) != previous {
                startSession(with: profile(named: selected) == nil ? "" : selected)
            }
        } catch {
            profilesConfig = nil
            profileLoadError = error
        }
    }

    var activeProfile: MediaProfile? {
        workflowSession.profileName.isEmpty ? nil : workflowSession.workingProfile
    }

    /// The profile as the app shows and runs it, gyroflow settings it leaves to
    /// the global preset filled in.
    func profile(named name: String) -> MediaProfile? {
        profilesConfig?.profile(named: name)
    }

    /// The profile without the file block it was read from. A save from the app
    /// keeps the block it loaded, while a reload reads the block as saved, so
    /// the block alone says nothing about whether the profile changed.
    private func settings(ofProfile name: String) -> MediaProfile? {
        guard var stored = profile(named: name) else { return nil }
        stored.fileNode = nil
        return stored
    }

    /// Create the profile for a camera found in the source chosen for it. Its
    /// camera, kind of media and file types come from that source's files.
    func createProfile(for found: SourceContents.NewCamera) -> String {
        let name = uniqueProfileName(found.kind.defaultProfileName)
        var profile = MediaProfile(type: found.kind.type)
        profile.exif = ExifConfig(make: found.kind.camera.make, model: found.kind.camera.model)
        profile.fileExtensions = found.extensions
        profile.sourceDir = found.source
        if profilesConfig == nil {
            profilesConfig = ProfilesConfig(gyroflow: nil, profiles: [:])
        }
        profilesConfig?.profiles[name] = profile
        writeProfiles()
        return name
    }

    /// A name no profile has yet, for a profile about to be created or copied.
    func uniqueProfileName(_ base: String) -> String {
        profilesConfig?.uniqueName(base) ?? base
    }

    /// Save an edited profile under `name` and write the file. `storedName` is
    /// the name it is stored under now, nil for a new one; a workflow that has
    /// the profile selected follows a rename. Throws `ProfileNameError` when
    /// another profile already has `name`, and nothing is written.
    func saveProfile(_ profile: MediaProfile, as name: String, replacing storedName: String?) throws {
        guard var config = profilesConfig else { return }
        try config.save(profile, as: name, replacing: storedName)
        profilesConfig = config
        writeProfiles()
        // The workflow runs the profile as it is now saved, under its new name.
        if let storedName, workflowSession.profileName == storedName {
            startSession(with: name)
        }
    }

    func deleteProfile(named name: String) {
        profilesConfig?.remove(named: name)
        writeProfiles()
        if workflowSession.profileName == name {
            startSession(with: "")
        }
    }

    /// Make `name` the workflow's profile. A different profile starts a fresh
    /// session from it — its folders, tags and steps — and clears the last run's
    /// log and table. Choosing the profile already selected changes nothing, so
    /// returning to the workflow keeps every choice made for it, the timezone
    /// included.
    func selectProfile(_ name: String) {
        guard name != workflowSession.profileName else { return }
        startSession(with: name)
    }

    /// A fresh session for `name` as it is stored now; an empty name is none.
    private func startSession(with name: String) {
        clearLog()
        workflowSession = WorkflowSession(
            profile: profile(named: name),
            profileName: name,
            gyroflowAvailable: gyroflowStatus.isInstalled
        )
    }

    func writeProfiles() {
        guard let config = profilesConfig else { return }
        do {
            try ProfileService.write(config, to: profilesLocation.path)
        } catch {
            profileLoadError = ProfileLoadError(
                message: Strings.Errors.profilesWriteFailed,
                filePath: profilesLocation.path,
                detail: error.localizedDescription
            )
        }
    }

    func clearLog() {
        logOutput = []
        transcript = RunTranscript()
        showRunSummary = false
        workflowSession.clearConflictReport()
    }

    func appendLog(_ line: LogLine) {
        guard line.isMachineReadable else {
            logOutput.append(line)
            return
        }
        guard let data = line.text.data(using: .utf8),
              let event = try? JSONDecoder().decode(PipelineEvent.self, from: data)
        else { return }
        if let notice = transcript.apply(event) {
            handle(notice)
        }
    }

    /// Act on what an event asked of the app beyond the table.
    private func handle(_ notice: RunTranscript.Notice) {
        switch notice {
        case .timezoneConflict(let kind, let providedTz, let fileTimezones):
            workflowSession.noteConflict()
            workflowSession.timezoneConflictType = kind
            workflowSession.timezoneConflictProvidedTz = providedTz
            workflowSession.timezoneConflictFileTimezones = fileTimezones
            // A dry run previews a provided-vs-embedded mismatch instead of
            // refusing it, so the conflict is recorded as data and the flagged
            // rows speak for themselves. Only a run the pipeline actually
            // refuses — an apply, or a mixed-zone batch in either mode — asks
            // the user to confirm.
            workflowSession.showTimezoneConflict =
                kind == .mixedTimezones || workflowSession.applyMode

        case .organizeConflict(let count, let files):
            workflowSession.organizeConflictCount = count
            workflowSession.organizeConflictFiles = files

        case .protectedSources(let files):
            workflowSession.noteConflict()
            workflowSession.protectedSourceFiles = files
            // A dry run previews the protected files anyway; only an apply is
            // refused, so only an apply asks.
            workflowSession.showProtectedSources = workflowSession.applyMode

        case .cameraMismatch(let mismatch):
            workflowSession.noteConflict()
            workflowSession.cameraMismatch = mismatch
            // A dry run previews files from another camera anyway; only an
            // apply is refused, so only an apply asks.
            workflowSession.showCameraMismatch = workflowSession.applyMode

        case .error(let message):
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
        let (process, stream) = launcher.run(script: "tools/download-gyroflow.sh", args: args)
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

    /// The run counts as started from the press of Run, not from the end of the media
    /// count: the count launches a script, and until it answers a second press would
    /// start a second pipeline and the form would still accept edits. A count that
    /// could not be taken starts the run.
    func startRun(
        afterCounting count: @escaping () async -> Int?,
        exceedsLimit: @escaping (Int) -> Bool,
        onOverLimit: @escaping (Int) -> Void,
        start: @escaping () -> Void
    ) {
        isRunning = true
        currentRunTask = Task {
            let fileCount = await count()
            await MainActor.run {
                guard !Task.isCancelled else { return }
                if let fileCount, exceedsLimit(fileCount) {
                    isRunning = false
                    currentRunTask = nil
                    onOverLimit(fileCount)
                } else {
                    start()
                }
            }
        }
    }

    /// Run the pipeline with the workflow's settings: Run, and every answer to a
    /// question a run raised, comes here.
    func runWorkflow(check: PythonRuntimeCheck = .system) {
        workflowSession.chooseSource()
        guard canRunPipeline(check: check) else { return }

        // An apply the user never previewed, and applying over the files the last
        // run reported blocked, both destroy files: the answers are taken before
        // anything runs — cancelling runs nothing.
        if workflowSession.requestDryRunAssentIfNeeded() { return }
        if workflowSession.requestOverwriteAssentIfNeeded() { return }

        let session = workflowSession
        let launcher = self.launcher
        let licenseStore = self.licenseStore
        startRun(
            afterCounting: {
                await SourceScan.mediaFileCount(
                    source: session.sourceDir.current,
                    extensions: session.workingProfile.fileExtensions ?? [],
                    launcher: launcher)
            },
            exceedsLimit: { licenseStore.exceedsLimit(fileCount: $0) },
            onOverLimit: { self.upgradePrompt = UpgradePrompt(fileCount: $0) },
            start: { self.startPipeline() })
    }

    /// Launch the pipeline and feed its output into the log and the table until
    /// it ends.
    func startPipeline() {
        clearLog()
        showInspector = true

        let (script, args) = workflowSession.buildPipelineArgs()
        workflowSession.noteRunStarted()

        let (process, stream) = launcher.run(script: script, args: args)
        currentProcess = process

        // The drain runs off the main actor, so a line can be on its way to it when
        // Cancel is pressed there: cancellation is checked again once on the main
        // actor, or that line would land after the cancelled line.
        currentRunTask = Task {
            for await line in stream {
                if Task.isCancelled { break }
                await MainActor.run {
                    guard !Task.isCancelled else { return }
                    appendLog(line)
                }
            }
            await MainActor.run {
                guard !Task.isCancelled else { return }
                finishRun()
            }
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

    /// The run-summary popup's "Show Output" button: dismiss the summary and
    /// switch the inspector to the log panel, so a run with too many failures to
    /// list in the alert can be inspected in full.
    func showOutputForRunSummary() {
        showRunSummary = false
        showInspector = true
        showLogOutput = true
    }

    func cancelRunning() {
        workflowSession.noteRunCancelled()
        currentRunTask?.cancel()
        currentRunTask = nil
        // The whole group, not just the script: the pipeline's exiftool child
        // would otherwise be re-parented to launchd and live on.
        currentProcess?.terminateGroup()
        currentProcess = nil
        isRunning = false
        // The drain task is cancelled above before the pipeline's own "Interrupted by
        // user" line can arrive, so that line never reaches the log. This is the app's
        // own line, not parsed from the pipeline's output.
        logOutput.append(LogLine(text: Strings.LogOutput.cancelled, stream: .stderr))
        transcript.dropLiveRow()
    }
}
