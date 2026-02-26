import SwiftUI

struct WorkflowView: View {
    @Bindable var state: AppState
    @State private var showUpgradeSheet = false
    @State private var detectedFileCount = 0
    private var licenseStore: LicenseStore { LicenseStore.shared }

    let defaultColumnWidth = 600.00

    private var companionExtensions: String {
        state.workflowSession.workingProfile.companionExtensions?.joined(separator: ", ") ?? ""
    }

    var body: some View {
        @Bindable var session = state.workflowSession
        ScrollView {
            VStack(spacing: 16) {
                profileSelector
                if !session.profileName.isEmpty {
                    stepsPipeline
                    executionBar
                }
            }
            .padding()
        }
        .onAppear {
            let name = state.workflowSession.profileName
            if !name.isEmpty {
                state.workflowSession = WorkflowSession(
                    profile: state.profilesConfig?.profiles[name],
                    profileName: name
                )
            }
        }
        .frame(minWidth: 340, idealWidth: defaultColumnWidth, maxWidth: defaultColumnWidth)
        .inspector(isPresented: $state.showLog) {
            VStack(spacing: 0) {
                if !state.diffTableRows.isEmpty || state.isRunning {
                    if state.workflowSession.applyMode {
                        FileProgressCardsView(
                            rows: state.visibleRows,
                            enabledSteps: state.workflowSession.availableSteps.filter {
                                $0.isAlwaysOn || state.workflowSession.enabledSteps.contains($0)
                            },
                            isRunning: state.isRunning
                        )
                    } else {
                        DiffTableView(rows: state.diffTableRows)
                    }
                }
                LogOutputView(lines: state.logOutput, onClear: { state.clearLog() })
            }
            .inspectorColumnWidth(min: 480, ideal: defaultColumnWidth)
        }
        .navigationTitle(Strings.Nav.workflow)
        .sheet(isPresented: $showUpgradeSheet) {
            UpgradeView(
                fileCount: detectedFileCount,
                store: licenseStore,
                onDismiss: { showUpgradeSheet = false },
                onUnlocked: {
                    showUpgradeSheet = false
                    runWorkflow()
                }
            )
        }
    }

    // MARK: - Profile selection

    private var profileSelector: some View {
        @Bindable var session = state.workflowSession
        return Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
            if let error = state.profileLoadError {
                GridRow {
                    Text("").gridColumnAlignment(.trailing)
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
            }

            GridRow {
                Text(Strings.Workflow.profileLabel).gridColumnAlignment(.trailing)
                ProfilePicker(selection: $session.profileName, state: state)
                    .onChange(of: session.profileName) { _, newValue in
                        state.workflowSession = WorkflowSession(
                            profile: state.profilesConfig?.profiles[newValue],
                            profileName: newValue
                        )
                    }
            }
        }
    }

    // MARK: - Pipeline steps

    private var stepsPipeline: some View {
        let steps = state.workflowSession.availableSteps
        return VStack(spacing: 0) {
            ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                stepCard(step)
                if index < steps.count - 1 {
                    stepArrow
                }
            }
        }
        .windowResizeBehavior(.automatic)
    }

    private func stepCard(_ step: PipelineStep) -> some View {
        let isActive = step.isAlwaysOn || state.workflowSession.enabledSteps.contains(step)
        return VStack(spacing: 0) {
            stepHeader(step, isActive: isActive)
            if isActive {
                stepOptionsContent(step)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(
                    isActive ? step.iconColor.opacity(step.isAlwaysOn ? 0.2 : 0.3)
                             : Color.secondary.opacity(0.5),
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

            VStack(alignment: .leading, spacing: 2) {
                Text(step.label)
                    .font(.system(size: 12, weight: .medium))
                Text(step.help)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            if step.isAlwaysOn {
                Image(systemName: "lock.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            } else if isActive && !state.workflowSession.isStepReady(step) {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundStyle(.yellow)
            } else {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isActive ? step.iconColor : .secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(isActive ? step.iconColor.opacity(step.isAlwaysOn ? 0.04 : 0.08) : .clear)
        .foregroundStyle(isActive ? .primary : .secondary)
        .contentShape(Rectangle())
    }

    private var stepArrow: some View {
        Image(systemName: "arrow.down")
            .font(.system(size: 11))
            .foregroundStyle(.tertiary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 4)
    }

    @ViewBuilder
    private func stepOptionsContent(_ step: PipelineStep) -> some View {
        switch step {
        case .ingest:
            Divider()
            ingestOptions
        case .tag:
            Divider()
            tagOptions
        case .organize:
            Divider()
            organizeOptions
        case .fixTimezone:
            Divider()
            fixTimezoneOptions
        case .archiveSource:
            Divider()
            archiveSourceOptions
        default:
            EmptyView()
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
                    .frame(width: 52, alignment: .trailing)
                CommaSeparatedField(items: $session.tags.value, placeholder: Strings.Workflow.tagPlaceholder)
            }
            HStack(spacing: 4) {
                Text(Strings.Workflow.cameraLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)
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
            if session.enabledSteps.contains(.fixTimezone) {
                HStack(spacing: 4) {
                    Toggle(Strings.Workflow.appendTimezoneToggle, isOn: $session.appendTimezoneToGroup)
                        .disabled(session.group.isEmpty)
                    HelpButton(Strings.Workflow.appendTimezoneHelp)
                }
            }
        }
        .padding(10)
    }

    private var fixTimezoneOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if !session.useTimezonePicker {
                    TextField(Strings.Workflow.timezonePlaceholder, text: $session.timezone.value)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 90)
                } else {
                    TimezonePickerView(selectedTimezone: $session.timezone.value)
                }
                Spacer()
                Button {
                    state.workflowSession.useTimezonePicker.toggle()
                } label: {
                    Image(systemName: session.useTimezonePicker ? "keyboard" : "globe")
                        .padding(4)
                }
                .contentShape(Rectangle())
                .help(session.useTimezonePicker ? Strings.Workflow.typeManuallyHelp : Strings.Workflow.pickFromListHelp)
            }
            .fieldError(session.validateTimezone())
        }
        .padding(10)
    }

    private var archiveSourceOptions: some View {
        @Bindable var session = state.workflowSession
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text(Strings.Workflow.sourceActionLabel)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Picker("", selection: $session.sourceAction) {
                    Text(Strings.Workflow.archiveOption).tag(SourceAction.archive)
                    Text(Strings.Workflow.deleteOption).tag(SourceAction.delete)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 220)
                HelpButton(Strings.Workflow.sourceActionHelp)
            }
            if session.sourceAction == .delete {
                Label(Strings.Workflow.deleteSourceWarning, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.yellow)
            }
        }
        .padding(10)
    }

    // MARK: - Execution

    private var executionBar: some View {
        @Bindable var session = state.workflowSession
        return Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
            Divider().gridCellUnsizedAxes(.horizontal)
            GridRow {
                Text(Strings.Workflow.modeLabel).gridColumnAlignment(.trailing)
                HStack(spacing: 12) {
                    Picker("", selection: $session.applyMode) {
                        Text(Strings.Workflow.dryRunOption).tag(false)
                        Text(Strings.Workflow.applyOption).tag(true)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 160)

                    Button(state.isRunning ? Strings.Workflow.runningButton : Strings.Workflow.runButton) { runWorkflow() }
                        .disabled(state.isRunning || !session.allStepsReady)
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)

                    if state.isRunning {
                        Button(Strings.Common.cancel, role: .destructive) { state.cancelRunning() }
                    }

                    Spacer()

                    Button {
                        state.showLog.toggle()
                    } label: {
                        Image(systemName: "terminal")
                            .foregroundStyle(state.showLog ? .primary : .secondary)
                    }
                    .buttonStyle(.borderless)
                    .help(state.showLog ? Strings.Workflow.hideLogHelp : Strings.Workflow.showLogHelp)
                }
            }
        }
    }

    // MARK: - Helpers

    private func destinationPreview(readyDir: String) -> String {
        let session = state.workflowSession
        var path = readyDir + "/YYYY"
        if !session.group.isEmpty {
            var groupName = session.group
            if session.appendTimezoneToGroup && session.enabledSteps.contains(.fixTimezone) && !session.timezone.current.isEmpty {
                groupName += " (\(session.timezone.current))"
            }
            path += "/\(groupName)"
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
        let fileCount = countMediaFiles()
        if fileCount > licenseStore.fileLimit {
            detectedFileCount = fileCount
            showUpgradeSheet = true
            return
        }

        state.clearLog()
        state.showLog = true
        state.isRunning = true

        let (script, args) = state.workflowSession.buildPipelineArgs()

        let (process, stream) = ScriptRunner.run(
            script: script,
            args: args,
            workingDir: state.scriptsDirectory
        )
        state.currentProcess = process

        Task {
            for await line in stream {
                await MainActor.run { state.appendLog(line) }
            }
            await MainActor.run {
                state.isRunning = false
                state.currentProcess = nil
            }
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
}
