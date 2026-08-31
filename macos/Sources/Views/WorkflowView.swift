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
    static let formWidth: CGFloat = 600

    private let optionLabelWidth: CGFloat = 52

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
                    pipelineStatusBar
                        .padding(.vertical, 8)
                    Rectangle()
                        .fill(Color.primary.opacity(0.12))
                        .frame(height: 1)
                        .shadow(color: .black.opacity(0.08), radius: 2, y: 1)
                }
            }
            .padding(.horizontal, 16)
            // No scroll view: the form is a fixed column of controls, and its height —
            // like its width — is its content's. Declaring it lets the window follow
            // (`windowResizability(.contentSize)`) when a step expands, instead of the
            // form scrolling inside a window that stayed put.
            VStack(spacing: 16) {
                if !session.profileName.isEmpty {
                    stepsPipeline
                        .disabled(state.isRunning)
                }
            }
            .padding(16)
            if !session.profileName.isEmpty {
                executionBar
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.bar)
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
        return VStack(alignment: .leading, spacing: 10) {
            if let error = state.profileLoadError {
                VStack(alignment: .leading, spacing: 6) {
                    Label(error.message, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                    if let detail = error.detail {
                        Text(detail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    HStack(spacing: 8) {
                        Text(error.filePath)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .textSelection(.enabled)
                        Button(Strings.Common.revealInFinder) {
                            NSWorkspace.shared.selectFile(error.filePath, inFileViewerRootedAtPath: "")
                        }
                        .controlSize(.small)
                    }
                }
            }

            HStack(spacing: 8) {
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

    // MARK: - Pipeline status bar

    private var pipelineStatusBar: some View {
        let steps = state.workflowSession.availableSteps
        let activeSteps = steps.filter { $0.isAlwaysOn || state.workflowSession.enabledSteps.contains($0) }
        return HStack(spacing: 0) {
            ForEach(Array(activeSteps.enumerated()), id: \.element.id) { index, step in
                HStack(spacing: 4) {
                    Image(systemName: step.systemImage)
                        .font(.system(size: 9))
                    Text(step.label)
                        .font(.system(size: 10, weight: .medium))
                }
                .foregroundStyle(.primary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 4)
                        .fill(step.iconColor.opacity(0.15))
                )
                .clipShape(RoundedRectangle(cornerRadius: 4))

                if index < activeSteps.count - 1 {
                    Image(systemName: "chevron.forward")
                        .font(.system(size: 7, weight: .bold))
                        .foregroundStyle(Color.secondary.opacity(0.3))
                        .padding(.horizontal, 1)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
    }

    // MARK: - Pipeline steps

    private var stepsPipeline: some View {
        let steps = state.workflowSession.availableSteps
        return VStack(spacing: 8) {
            ForEach(steps) { step in
                stepCard(step)
            }
        }
    }

    private func stepCard(_ step: PipelineStep) -> some View {
        let isActive = step.isAlwaysOn || state.workflowSession.enabledSteps.contains(step)
        return VStack(spacing: 0) {
            stepHeader(step, isActive: isActive)
            if isActive {
                Divider()
                stepOptionsContent(step)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(
                    isActive ? step.iconColor.opacity(step.isAlwaysOn ? 0.12 : 0.2)
                             : Color.secondary.opacity(0.15),
                    lineWidth: 1
                )
        )
    }

    @ViewBuilder
    private func stepHeader(_ step: PipelineStep, isActive: Bool) -> some View {
        if step.isAlwaysOn {
            stepHeaderContent(step, isActive: isActive)
        } else {
            Button {
                if isActive {
                    state.workflowSession.enabledSteps.remove(step)
                } else {
                    state.workflowSession.enabledSteps.insert(step)
                }
            } label: {
                stepHeaderContent(step, isActive: isActive)
            }
            .buttonStyle(.plain)
        }
    }

    private func stepHeaderContent(_ step: PipelineStep, isActive: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: step.systemImage)
                .font(.system(size: 12))
                .foregroundStyle(isActive ? step.iconColor : .secondary)
                .frame(width: 16)

            Text(step.label)
                .font(.system(size: 12, weight: .medium))

            HelpButton(step.help)

            Spacer()

            if step.isAlwaysOn {
                Text(Strings.Workflow.requiredLabel)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.tertiary)
            } else {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isActive ? step.iconColor : .secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(isActive ? step.iconColor.opacity(step.isAlwaysOn ? 0.03 : 0.05) : .clear)
        .foregroundStyle(isActive ? .primary : .secondary)
        .contentShape(Rectangle())
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
        return VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    TextField(Strings.Workflow.sourceDirPlaceholder, text: $session.sourceDir.value)
                        .textFieldStyle(.roundedBorder)
                        .truncationMode(.head)
                        .help(session.sourceDir.current)
                    Button(Strings.Common.browse) { pickSourceDir() }
                        .controlSize(.small)
                }
                .fieldError(validateDirectory(session.sourceDir.current))
            }

            HStack(spacing: 4) {
                Toggle(isOn: $session.copyCompanionFiles) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(Strings.Workflow.copyCompanionToggle)
                        if companionExtensions.isEmpty {
                            Text(Strings.Workflow.noCompanionFiles)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Text(companionExtensions)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .disabled(companionExtensions.isEmpty)
                HelpButton(Strings.Workflow.copyCompanionHelp)
            }
        }
        .padding(10)
    }

    private var tagOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text(Strings.Workflow.tagsLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: optionLabelWidth, alignment: .trailing)
                CommaSeparatedField(items: $session.tags.value, placeholder: Strings.Workflow.tagPlaceholder)
            }
            HStack(spacing: 4) {
                Text(Strings.Workflow.cameraLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: optionLabelWidth, alignment: .trailing)
                let make = session.workingProfile.exif?.make ?? ""
                let model = session.workingProfile.exif?.model ?? ""
                let device = [make, model].filter { !$0.isEmpty }.joined(separator: " ")
                Text(device.isEmpty ? "—" : device)
                    .font(.caption)
                    .foregroundStyle(device.isEmpty ? .tertiary : .primary)
            }
        }
        .padding(10)
    }

    private var organizeOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    TextField(Strings.Workflow.readyDirPlaceholder, text: $session.readyDir.value)
                        .textFieldStyle(.roundedBorder)
                        .truncationMode(.head)
                        .help(session.readyDir.current)
                    Button(Strings.Common.browse) { pickReadyDir() }
                        .controlSize(.small)
                }
                .fieldError(validateDirectory(session.readyDir.current))
            }
            Text(session.readyDir.current.isEmpty ? Strings.Workflow.readyDirRequired : destinationPreview(readyDir: session.readyDir.current))
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 4) {
                HelpLabel(Strings.Workflow.groupLabel, help: Strings.Workflow.groupHelp)
                TextField(Strings.Workflow.groupPlaceholder, text: $session.group)
                    .textFieldStyle(.roundedBorder)
            }
        }
        .padding(10)
    }

    private var fixTimestampsOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TimezonePickerView(selectedTimezone: $session.timezone.value)
                Spacer()
            }
            .fieldError(session.validateTimezone())
            let parseable = hasParseableFilenames()
            if parseable {
                HStack(spacing: 4) {
                    Text(Strings.Workflow.timestampSourceLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Picker("", selection: $session.inferFromFilenames) {
                        Text(Strings.Workflow.timestampSourceMetadata).tag(false)
                        Text(Strings.Workflow.timestampSourceFilenames).tag(true)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .fixedSize()
                    Spacer()
                }
            }

            HStack(spacing: 4) {
                HelpLabel(Strings.Workflow.timeOffsetLabel, help: Strings.Workflow.timeOffsetHelp)
                TextField(Strings.Workflow.timeOffsetPlaceholder, value: $session.timeOffsetSeconds, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 90)
                Spacer()
            }

            HStack(spacing: 4) {
                Toggle(Strings.Workflow.updateFilenameDatesToggle, isOn: $session.updateFilenameDates)
                    .disabled(!parseable)
                HelpButton(Strings.Workflow.updateFilenameDatesHelp)
            }

            if let preview = fixTimestampPreview {
                Text(preview)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(10)
        .onChange(of: session.sourceDir.value) { _, _ in
            if !hasParseableFilenames() && session.inferFromFilenames {
                session.inferFromFilenames = false
            }
        }
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
        return VStack(alignment: .leading, spacing: 6) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    TextField(Strings.Workflow.archiveDestinationPlaceholder, text: $session.archiveDestination)
                        .textFieldStyle(.roundedBorder)
                        .truncationMode(.head)
                        .help(session.archiveDestination)
                    Button(Strings.Common.browse) { pickArchiveDestination() }
                        .controlSize(.small)
                    HelpButton(Strings.Workflow.archiveSourceHelp)
                }
                .fieldError(session.validateArchiveSource())
            }
            HStack(spacing: 6) {
                Toggle(Strings.Workflow.renameSourceDirToggle, isOn: $session.renameSourceDir)
                TextField("", text: $session.archivedName)
                    .textFieldStyle(.roundedBorder)
                    .disabled(!session.renameSourceDir)
                    .foregroundStyle(session.renameSourceDir ? .primary : .secondary)
            }
        }
        .padding(10)
    }

    private var gyroflowOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                HelpLabel(Strings.Profiles.maxZoomLabel, help: Strings.Profiles.maxZoomHelp)
                TextField("", value: gyroflowBinding(\.maxZoom), format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 70)
                Spacer()
            }
            HStack(spacing: 4) {
                HelpLabel(Strings.Profiles.adaptiveZoomWindowLabel, help: Strings.Profiles.adaptiveZoomWindowHelp)
                TextField("", value: gyroflowBinding(\.adaptiveZoomWindow), format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 70)
                Spacer()
            }
            HStack(spacing: 4) {
                HelpLabel(Strings.Profiles.adaptiveZoomMethodLabel, help: Strings.Profiles.adaptiveZoomMethodHelp)
                Picker("", selection: gyroflowZoomMethodBinding) {
                    ForEach(AdaptiveZoomMethod.allCases) { method in
                        Text(method.label).tag(method)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .fixedSize()
                Spacer()
            }
        }
        .padding(10)
    }

    private func gyroflowBinding(_ keyPath: WritableKeyPath<StabilizationSettings, Double?>) -> Binding<Double?> {
        Binding(
            get: { state.workflowSession.workingProfile.gyroflowSettings?[keyPath: keyPath] },
            set: { newValue in
                if state.workflowSession.workingProfile.gyroflowSettings == nil {
                    state.workflowSession.workingProfile.gyroflowSettings = StabilizationSettings()
                }
                state.workflowSession.workingProfile.gyroflowSettings?[keyPath: keyPath] = newValue
            }
        )
    }

    private var gyroflowZoomMethodBinding: Binding<AdaptiveZoomMethod> {
        Binding(
            get: {
                AdaptiveZoomMethod(rawValue: state.workflowSession.workingProfile.gyroflowSettings?.adaptiveZoomMethod ?? 1) ?? .dynamic
            },
            set: { newValue in
                if state.workflowSession.workingProfile.gyroflowSettings == nil {
                    state.workflowSession.workingProfile.gyroflowSettings = StabilizationSettings()
                }
                state.workflowSession.workingProfile.gyroflowSettings?.adaptiveZoomMethod = newValue.rawValue
            }
        )
    }

    // MARK: - Execution

    private var executionBar: some View {
        @Bindable var session = state.workflowSession
        return HStack(spacing: 12) {
            Picker("", selection: $session.applyMode) {
                Text(Strings.Workflow.dryRunOption).tag(false)
                Text(Strings.Workflow.applyOption).tag(true)
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .fixedSize()
            .disabled(state.isRunning)

            Button(state.isRunning ? Strings.Workflow.runningButton : Strings.Workflow.runButton) {
                state.workflowSession.clearRunAssent()
                runWorkflow()
            }
                .disabled(state.isRunning || !session.allStepsReady)
                .keyboardShortcut(.return, modifiers: .command)
                .buttonStyle(.borderedProminent)

            if state.isRunning {
                Button(Strings.Common.cancel, role: .destructive) { state.cancelRunning() }
            }

            Spacer()
        }
    }

    // MARK: - Inspector bars


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

    private func hasParseableFilenames() -> Bool {
        let session = state.workflowSession
        let extensions = (session.workingProfile.fileExtensions ?? []).map {
            $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        }
        guard !extensions.isEmpty else { return false }
        let dir = session.sourceDir.current
        guard !dir.isEmpty else { return false }
        guard let enumerator = FileManager.default.enumerator(
            at: URL(fileURLWithPath: dir),
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return false }
        for item in enumerator {
            guard let url = item as? URL,
                  extensions.contains(url.pathExtension.lowercased())
            else { continue }
            if FilenamePatterns.hasParseableTimestamp(url.lastPathComponent, scriptsDirectory: state.scriptsDirectory) {
                return true
            }
        }
        return false
    }

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
            profilesPath: state.resolvedProfilesPath
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

    private func pickSourceDir() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.workflowSession.sourceDir.value = url.path
        }
    }

    private func pickReadyDir() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.workflowSession.readyDir.value = url.path
        }
    }

    private func pickArchiveDestination() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.workflowSession.archiveDestination = url.path
        }
    }
}
