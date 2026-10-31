import SwiftUI

struct WorkflowView: View {
    @Bindable var state: AppState
    @State private var upgradePrompt: UpgradePrompt?
    private var licenseStore: LicenseStore { LicenseStore.shared }

    private struct UpgradePrompt: Identifiable {
        let fileCount: Int
        var id: Int { fileCount }
    }

    /// The form's one design width. Its controls are text fields, which have no
    /// intrinsic width, so the form cannot be sized from its content; everything around
    /// it — the panel's share, the window's minimum — is derived from this by the layout
    /// system rather than declared again.
    static let formWidth = Theme.Size.form

    private var companionExtensions: String {
        state.workflowSession.workingProfile.companionExtensions?.joined(separator: ", ") ?? ""
    }

    var body: some View {
        @Bindable var session = state.workflowSession
        VStack(spacing: 0) {
            VStack(spacing: 0) {
                profileSelector
                    .disabled(state.isRunning)
                    .padding(.vertical)
                if !session.profileName.isEmpty {
                    ChipBar(chips: session.availableSteps
                        .filter { $0.isAlwaysOn || session.enabledSteps.contains($0) }
                        .map { Chip(id: $0.id, icon: $0.systemImage, label: $0.label, tint: $0.iconColor) })
                        .padding(.vertical, Theme.Space.lg)
                    Rectangle()
                        .fill(Theme.Text.primaryColor.opacity(Theme.Tint.rule))
                        .frame(height: Theme.Stroke.hairline)
                        .shadow(color: Theme.Surface.shadow, radius: Theme.Shadow.radius, y: Theme.Shadow.offsetY)
                }
            }
            .padding(.horizontal, Theme.Space.xxxl)
            // The steps take whatever height the window has, scrolling when they need
            // more: the window keeps the size it opened at, or the user gave it, however
            // many steps a profile has or how many are expanded.
            ScrollView {
                VStack(spacing: Theme.Space.xxxl) {
                    if !session.profileName.isEmpty {
                        stepsPipeline
                            .disabled(state.isRunning)
                    }
                }
                .padding(Theme.Space.xxxl)
            }
            .scrollBounceBehavior(.basedOnSize)
            if !session.profileName.isEmpty {
                executionBar
            }
        }
        .onAppear {
            let name = state.workflowSession.profileName
            if !name.isEmpty {
                state.workflowSession = WorkflowSession(
                    profile: state.profilesConfig?.profiles[name],
                    profileName: name,
                    gyroflowAvailable: state.gyroflowStatus.isInstalled
                )
            }
        }
        .frame(width: Self.formWidth)
        .navigationTitle(Strings.Nav.workflow)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    state.showInspector.toggle()
                } label: {
                    Image(systemName: "sidebar.trailing")
                }
                .help(state.showInspector ? Strings.Workflow.hideInspectorHelp : Strings.Workflow.showInspectorHelp)
            }
        }
        .sheet(item: $upgradePrompt) { prompt in
            UpgradeView(
                fileCount: prompt.fileCount,
                store: licenseStore,
                onDismiss: { upgradePrompt = nil },
                onUnlocked: {
                    upgradePrompt = nil
                    runWorkflow()
                }
            )
        }
        .alert(
            Strings.Workflow.timezoneConflictTitle,
            isPresented: $state.workflowSession.showTimezoneConflict
        ) {
            Button(Strings.Workflow.forceTimezoneButton, role: .destructive) {
                state.workflowSession.grantTimezoneAssent()
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showTimezoneConflict = false
            }
        } message: {
            Text(timezoneConflictMessage)
        }
        .alert(
            Strings.Workflow.overwriteConflictTitle,
            isPresented: $state.workflowSession.showOverwriteConflict
        ) {
            Button(Strings.Workflow.overwriteButton, role: .destructive) {
                state.workflowSession.grantOverwriteAssent()
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showOverwriteConflict = false
            }
        } message: {
            Text(Strings.Workflow.overwriteConflictMessage(
                count: state.workflowSession.organizeConflictCount))
        }
        .alert(
            Strings.Workflow.cameraMismatchTitle,
            isPresented: $state.workflowSession.showCameraMismatch
        ) {
            Button(Strings.Workflow.allowCameraMismatchButton, role: .destructive) {
                state.workflowSession.grantCameraMismatchAssent()
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showCameraMismatch = false
            }
        } message: {
            if let mismatch = state.workflowSession.cameraMismatch {
                Text(Strings.Workflow.cameraMismatchMessage(
                    count: mismatch.files.count,
                    found: mismatch.foundName,
                    expected: mismatch.expected?.name ?? ""))
            }
        }
        .alert(
            Strings.Workflow.protectedSourcesTitle,
            isPresented: $state.workflowSession.showProtectedSources
        ) {
            Button(Strings.Workflow.unlockProtectedButton) {
                state.workflowSession.grantUnlockProtectedAssent()
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showProtectedSources = false
            }
        } message: {
            Text(Strings.Workflow.protectedSourcesMessage(
                files: state.workflowSession.protectedSourceFiles))
        }
        .alert(
            state.workflowSession.dryRunStaleReason == .settingsChanged
                ? Strings.Workflow.dryRunStaleTitle
                : Strings.Workflow.noDryRunTitle,
            isPresented: $state.workflowSession.showDryRunStale
        ) {
            Button(Strings.Workflow.dryRunFirstButton) {
                state.workflowSession.startDryRunInstead()
                runWorkflow()
            }
            .keyboardShortcut(.defaultAction)
            Button(Strings.Workflow.applyAnywayButton, role: .destructive) {
                state.workflowSession.grantDryRunStaleAssent()
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showDryRunStale = false
            }
        } message: {
            Text(state.workflowSession.dryRunStaleReason == .settingsChanged
                 ? Strings.Workflow.dryRunStaleMessage
                 : Strings.Workflow.noDryRunMessage)
        }
        .alert(
            state.runSummary?.mode == .applied
                ? Strings.Workflow.runCompleteAppliedTitle
                : Strings.Workflow.runCompleteDryRunTitle,
            isPresented: $state.showRunSummary
        ) {
            Button(Strings.Common.done) { state.showRunSummary = false }
                .keyboardShortcut(.defaultAction)
            if (state.runSummary?.failed ?? 0) > 0 {
                Button(Strings.Workflow.showOutputButton) {
                    state.showOutputForRunSummary()
                }
            }
        } message: {
            Text(runSummaryMessage)
        }
        .alert(
            Strings.Errors.commandLineToolsTitle,
            isPresented: Binding(
                get: { state.pythonRuntimeAlert != nil },
                set: { if !$0 { state.pythonRuntimeAlert = nil } }
            )
        ) {
            Button(Strings.Common.done) { state.pythonRuntimeAlert = nil }
        } message: {
            Text(state.pythonRuntimeAlert ?? "")
        }
    }

    private var runSummaryMessage: String {
        guard let summary = state.runSummary else { return "" }
        var lines = [Strings.Workflow.runSummaryCounts(
            processed: summary.processed,
            changed: summary.changed,
            mode: summary.mode)]
        lines.append(summary.mode == .applied
                     ? Strings.Workflow.runSummaryApplied
                     : Strings.Workflow.runSummaryDryRun)
        if summary.failed > 0 {
            lines.append(Strings.Workflow.runSummaryFailed(
                count: summary.failed,
                files: summary.failedFiles))
        }
        if summary.mode == .dryRun, let mismatch = state.workflowSession.cameraMismatch {
            lines.append(Strings.Workflow.runSummaryCameraMismatch(
                count: mismatch.files.count,
                found: mismatch.foundName,
                expected: mismatch.expected?.name ?? ""))
        }
        return lines.joined(separator: "\n\n")
    }

    private var timezoneConflictMessage: String {
        let session = state.workflowSession
        guard let fileTimezones = session.timezoneConflictFileTimezones else {
            return ""
        }
        if session.timezoneConflictType == "mixed_timezones" {
            let groups = fileTimezones.map { tz, files in
                "\(tz): \(files.count) file\(files.count == 1 ? "" : "s")"
            }.sorted().joined(separator: "\n")
            return Strings.Workflow.mixedTimezonesMessage(groups: groups)
        } else {
            let provided = session.timezoneConflictProvidedTz ?? ""
            let existing = fileTimezones.keys.sorted().joined(separator: ", ")
            return Strings.Workflow.providedMismatchMessage(provided: provided, existing: existing)
        }
    }

    // MARK: - Profile selection

    private var profileSelector: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            if let error = state.profileLoadError {
                VStack(alignment: .leading, spacing: Theme.Space.md) {
                    Label(error.message, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(Theme.Status.failure)
                    if let detail = error.detail {
                        Text(detail)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Text.secondary)
                            .textSelection(.enabled)
                    }
                    HStack(spacing: Theme.Space.lg) {
                        Text(error.filePath)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Text.tertiary)
                            .textSelection(.enabled)
                        Button(Strings.Common.revealInFinder) {
                            NSWorkspace.shared.selectFile(error.filePath, inFileViewerRootedAtPath: "")
                        }
                        .controlSize(.small)
                    }
                }
            }

            HStack(spacing: Theme.Space.lg) {
                Text(Strings.Workflow.profileLabel)
                ProfilePicker(selection: $session.profileName, state: state)
                    .onChange(of: session.profileName) { _, newValue in
                        state.clearLog()
                        state.workflowSession = WorkflowSession(
                            profile: state.profilesConfig?.profiles[newValue],
                            profileName: newValue,
                            gyroflowAvailable: state.gyroflowStatus.isInstalled
                        )
                    }
            }
        }
    }

    // MARK: - Pipeline steps

    private var stepsPipeline: some View {
        let session = state.workflowSession
        return VStack(spacing: Theme.Space.lg) {
            ForEach(session.availableSteps) { step in
                Card(
                    title: step.label,
                    icon: step.systemImage,
                    tint: step.iconColor,
                    help: step.help,
                    isRequired: step.isAlwaysOn,
                    isActive: step.isAlwaysOn || session.enabledSteps.contains(step),
                    onToggle: { session.toggle(step) }
                ) {
                    stepOptionsContent(step)
                }
            }
        }
    }

    @ViewBuilder
    private func stepOptionsContent(_ step: PipelineStep) -> some View {
        switch step {
        case .ingest:
            ingestOptions
        case .tag:
            tagOptions
        case .organize:
            organizeOptions
        case .fixTimestamps:
            fixTimestampsOptions
        case .gyroflow:
            gyroflowOptions
        case .archiveSource:
            archiveSourceOptions
        }
    }

    // MARK: - Inline step options

    private var ingestOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            PathField(
                placeholder: Strings.Workflow.sourceDirPlaceholder,
                path: $session.sourceDir.value,
                error: validateDirectory(session.sourceDir.current),
                onCommit: { session.chooseSource() })
            ToggleRow(
                title: Strings.Workflow.copyCompanionToggle,
                caption: companionExtensions.isEmpty ? Strings.Workflow.noCompanionFiles : companionExtensions,
                isOn: $session.copyCompanionFiles,
                isEnabled: !companionExtensions.isEmpty,
                help: Strings.Workflow.copyCompanionHelp)
        }
    }

    private var tagOptions: some View {
        @Bindable var session = state.workflowSession
        let make = session.workingProfile.exif?.make ?? ""
        let model = session.workingProfile.exif?.model ?? ""
        let device = [make, model].filter { !$0.isEmpty }.joined(separator: " ")
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            OptionGroup {
                OptionRow(label: Strings.Workflow.tagsLabel) {
                    CommaSeparatedField(items: $session.tags.value, placeholder: Strings.Workflow.tagPlaceholder)
                }
                OptionRow(label: Strings.Workflow.cameraLabel) {
                    Text(device.isEmpty ? "—" : device)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(device.isEmpty ? Theme.Text.tertiary : Theme.Text.primary)
                }
            }
        }
    }

    private var organizeOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            PathField(
                placeholder: Strings.Workflow.readyDirPlaceholder,
                path: $session.readyDir.value,
                error: validateDirectory(session.readyDir.current))
            Text(session.readyDir.current.isEmpty ? Strings.Workflow.readyDirRequired : destinationPreview(readyDir: session.readyDir.current))
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Text.secondary)
            OptionGroup {
                OptionRow(label: Strings.Workflow.groupLabel, help: Strings.Workflow.groupHelp) {
                    TextField(Strings.Workflow.groupPlaceholder, text: $session.group)
                        .textFieldStyle(.roundedBorder)
                }
            }
        }
    }

    private var fixTimestampsOptions: some View {
        @Bindable var session = state.workflowSession
        let parseable = session.sourceHasTimestampedNames
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            HStack(spacing: Theme.Space.md) {
                TimezonePickerView(selectedTimezone: $session.timezone.value)
                Spacer()
            }
            .fieldError(session.validateTimezone())
            OptionGroup {
                if parseable {
                    OptionRow(label: Strings.Workflow.timestampSourceLabel) {
                        Picker("", selection: $session.inferFromFilenames) {
                            Text(Strings.Workflow.timestampSourceMetadata).tag(false)
                            Text(Strings.Workflow.timestampSourceFilenames).tag(true)
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .fixedSize()
                    }
                }

                OptionRow(label: Strings.Workflow.timeOffsetLabel, help: Strings.Workflow.timeOffsetHelp) {
                    TextField(Strings.Workflow.timeOffsetPlaceholder, value: $session.timeOffsetSeconds, format: .number)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: Theme.Size.numberField)
                }
            }

            ToggleRow(
                title: Strings.Workflow.updateFilenameDatesToggle,
                isOn: $session.updateFilenameDates,
                isEnabled: parseable,
                help: Strings.Workflow.updateFilenameDatesHelp)

            if let preview = fixTimestampPreview {
                Text(preview)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Text.tertiary)
            }
        }
        .task(id: SourceRead(session: ObjectIdentifier(session), source: session.chosenSource)) {
            let source = session.chosenSource
            let found = await FilenamePatterns.sourceHasTimestampedNames(
                source,
                extensions: session.workingProfile.fileExtensions ?? [],
                scriptsDirectory: state.scriptsDirectory)
            guard !Task.isCancelled else { return }
            session.noteTimestampedNames(found, in: source)
        }
    }

    /// A new session (a profile picked) or a newly chosen source is read afresh.
    private struct SourceRead: Hashable {
        let session: ObjectIdentifier
        let source: String
    }

    var fixTimestampPreview: String? {
        let session = state.workflowSession
        guard session.enabledSteps.contains(.fixTimestamps) else { return nil }

        var parts: [String] = []
        if session.inferFromFilenames {
            if let option = session.timezoneOption {
                parts.append(option.offsets.count > 1
                    ? Strings.Workflow.fixTimestampSourceFilenamesZoneMultiHint(city: option.city)
                    : Strings.Workflow.fixTimestampSourceFilenamesZoneHint(city: option.city, offsetLabel: option.offsetLabel))
            } else {
                parts.append(Strings.Workflow.fixTimestampSourceFilenamesHint)
            }
        }
        if let offset = session.timeOffsetSeconds, offset != 0 {
            let sign = offset > 0 ? "+" : ""
            parts.append(Strings.Workflow.fixTimestampShiftHint(sign: sign, offset: offset))
        }
        if let option = session.timezoneOption, !session.inferFromFilenames {
            parts.append(option.offsets.count > 1
                ? Strings.Workflow.fixTimestampZoneMultiHint(city: option.city)
                : Strings.Workflow.fixTimestampZoneHint(city: option.city, offsetLabel: option.offsetLabel))
        }
        if session.updateFilenameDates {
            parts.append(Strings.Workflow.fixTimestampRenameHint)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var archiveSourceOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: Theme.Space.xl) {
            PathField(
                placeholder: Strings.Workflow.archiveDestinationPlaceholder,
                path: $session.archiveDestination,
                error: session.validateArchiveSource(),
                help: Strings.Workflow.archiveSourceHelp)
            HStack(spacing: Theme.Space.md) {
                Toggle(Strings.Workflow.renameSourceDirToggle, isOn: $session.renameSourceDir)
                TextField("", text: $session.archivedName)
                    .textFieldStyle(.roundedBorder)
                    .disabled(!session.renameSourceDir)
                    .foregroundStyle(session.renameSourceDir ? Theme.Text.primary : Theme.Text.secondary)
            }
        }
    }

    private var gyroflowOptions: some View {
        @Bindable var session = state.workflowSession
        return OptionGroup {
            GyroflowSettingsRows(settings: $session.workingProfile.gyroflowSettings)
        }
    }

    // MARK: - Execution

    private var executionBar: some View {
        @Bindable var session = state.workflowSession
        return ActionBar(
            modes: [
                ActionMode(title: Strings.Workflow.dryRunOption, value: false),
                ActionMode(title: Strings.Workflow.applyOption, value: true),
            ],
            mode: $session.applyMode,
            primaryTitle: state.isRunning ? Strings.Workflow.runningButton : Strings.Workflow.runButton,
            cancelTitle: Strings.Common.cancel,
            isRunning: state.isRunning,
            canRun: session.allStepsReady,
            onRun: {
                state.workflowSession.clearRunAssent()
                runWorkflow()
            },
            onCancel: { state.cancelRunning() })
    }

    // MARK: - Helpers

    private func destinationPreview(readyDir: String) -> String {
        let session = state.workflowSession
        var path = readyDir + "/YYYY"
        if !session.group.isEmpty {
            path += "/\(session.group)"
        }
        path += "/YYYY-MM-DD"
        return path
    }

    // MARK: - Actions

    private func countMediaFiles() -> Int {
        let session = state.workflowSession
        let extensions = (session.workingProfile.fileExtensions ?? []).map {
            $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        }
        guard !extensions.isEmpty else { return 0 }
        let dir = session.sourceDir.current
        guard !dir.isEmpty else { return 0 }
        guard let enumerator = FileManager.default.enumerator(
            at: URL(fileURLWithPath: dir),
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return 0 }
        return enumerator.reduce(0) { count, item in
            guard let url = item as? URL else { return count }
            return extensions.contains(url.pathExtension.lowercased()) ? count + 1 : count
        }
    }

    private func runWorkflow() {
        state.workflowSession.chooseSource()
        guard state.canRunPipeline() else { return }

        // An apply the user never previewed, and applying over the files the last
        // run reported blocked, both destroy files: the answers are taken before
        // anything runs — cancelling runs nothing.
        if state.workflowSession.requestDryRunAssentIfNeeded() { return }
        if state.workflowSession.requestOverwriteAssentIfNeeded() { return }

        let fileCount = countMediaFiles()
        if licenseStore.exceedsLimit(fileCount: fileCount) {
            upgradePrompt = UpgradePrompt(fileCount: fileCount)
            return
        }

        state.clearLog()
        state.showInspector = true
        state.isRunning = true

        let (script, args) = state.workflowSession.buildPipelineArgs()
        state.workflowSession.noteRunStarted()

        let (process, stream) = ScriptRunner.run(
            script: script,
            args: args,
            workingDir: state.scriptsDirectory,
            profilesPath: state.profilesLocation.path
        )
        state.currentProcess = process

        state.currentRunTask = Task {
            for await line in stream {
                if Task.isCancelled { break }
                await MainActor.run { state.appendLog(line) }
            }
            guard !Task.isCancelled else { return }
            await MainActor.run { state.finishRun() }
        }
    }
}
