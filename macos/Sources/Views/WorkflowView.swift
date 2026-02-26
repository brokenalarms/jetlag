import SwiftUI

struct WorkflowView: View {
    @Bindable var state: AppState
    @State private var sourceDir = Dirtyable("")
    @State private var timezone = Dirtyable("")
    @FocusState private var sourceDirFocused: Bool
    @FocusState private var timezoneFocused: Bool
    @State private var showUpgradeSheet = false
    @State private var detectedFileCount = 0
    private var licenseStore: LicenseStore { LicenseStore.shared }

    private var companionExtensions: String {
        state.activeProfile?.companionExtensions?.joined(separator: ", ") ?? ""
    }

    private var sourceDirError: String? {
        let path = sourceDir.current
        guard !path.isEmpty else { return nil }
        var isDir: ObjCBool = false
        if !FileManager.default.fileExists(atPath: path, isDirectory: &isDir) {
            return Strings.Errors.directoryNotFound
        } else if !isDir.boolValue {
            return Strings.Errors.pathIsFile
        }
        return nil
    }

    private var timezoneError: String? {
        if state.useTimezonePicker { return nil }
        if !state.enabledSteps.contains(.fixTimezone) { return nil }
        let tz = timezone.current
        if tz.isEmpty { return Strings.Workflow.timezoneRequired }
        if !tz.contains(/^[+-]\d{4}$/) { return Strings.Workflow.timezoneFormatHelp }
        return nil
    }

    private var timezoneIsValid: Bool { timezoneError == nil }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                profileSelector
                if !state.selectedProfile.isEmpty {
                    stepsPipeline
                    executionBar
                }
            }
            .padding()
        }
        .onChange(of: sourceDir.current) { _, new in state.sourceDir = new }
        .onChange(of: timezone.current) { _, new in state.timezone = new }
        .frame(minWidth: 340)
        .inspector(isPresented: $state.showLog) {
            VStack(spacing: 0) {
                if !state.diffTableRows.isEmpty || state.isRunning {
                    DiffTableView(rows: state.diffTableRows)
                }
                LogOutputView(lines: state.logOutput, onClear: { state.clearLog() })
            }
            .inspectorColumnWidth(min: 480, ideal: 680)
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
        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
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
                ProfilePicker(selection: $state.selectedProfile, state: state)
                    .onChange(of: state.selectedProfile) { _, newValue in
                        state.resetWorkflowFields(for: newValue)
                        sourceDir = Dirtyable(state.sourceDir)
                        timezone = Dirtyable(state.timezone)
                    }
            }
        }
    }

    // MARK: - Pipeline steps

    private var stepsPipeline: some View {
        let steps = state.availableSteps
        return VStack(spacing: 0) {
            ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                stepCard(step)
                if index < steps.count - 1 {
                    stepArrow
                }
            }
        }
    }

    private func stepCard(_ step: PipelineStep) -> some View {
        let isActive = step.isAlwaysOn || state.enabledSteps.contains(step)
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
                    state.enabledSteps.remove(step)
                } else {
                    state.enabledSteps.insert(step)
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
            } else if isActive && !state.isStepReady(step) {
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
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    TextField(Strings.Workflow.sourceDirPlaceholder, text: $sourceDir.value)
                        .textFieldStyle(.roundedBorder)
                        .focused($sourceDirFocused)
                        .onChange(of: sourceDirFocused) { _, focused in
                            if !focused { sourceDir.markTouched() }
                        }
                    Button(Strings.Common.browse) { pickSourceDir() }
                        .controlSize(.small)
                }
                .fieldError(sourceDirError, show: sourceDir.touched)
            }

            HStack(spacing: 4) {
                Toggle(isOn: $state.copyCompanionFiles) {
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
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text(Strings.Workflow.tagsLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)
                TextField(Strings.Workflow.tagPlaceholder, text: $state.tags)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
            }
            HStack(spacing: 4) {
                Text(Strings.Workflow.cameraLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)
                TextField(Strings.Workflow.makePlaceholder, text: $state.exifMake)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                TextField(Strings.Workflow.modelPlaceholder, text: $state.exifModel)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
            }
        }
        .padding(10)
    }

    private var organizeOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TextField(Strings.Workflow.readyDirPlaceholder, text: $state.readyDir)
                    .textFieldStyle(.roundedBorder)
                Button(Strings.Common.browse) { pickReadyDir() }
                    .controlSize(.small)
            }
            Text(state.readyDir.isEmpty ? Strings.Workflow.readyDirRequired : destinationPreview(readyDir: state.readyDir))
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 4) {
                HelpLabel(Strings.Workflow.groupLabel, help: Strings.Workflow.groupHelp)
                TextField(Strings.Workflow.groupPlaceholder, text: $state.group)
                    .textFieldStyle(.roundedBorder)
            }
            if state.enabledSteps.contains(.fixTimezone) {
                HStack(spacing: 4) {
                    Toggle(Strings.Workflow.appendTimezoneToggle, isOn: $state.appendTimezoneToGroup)
                        .disabled(state.group.isEmpty)
                    HelpButton(Strings.Workflow.appendTimezoneHelp)
                }
            }
        }
        .padding(10)
    }

    private var fixTimezoneOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if !state.useTimezonePicker {
                    TextField(Strings.Workflow.timezonePlaceholder, text: $timezone.value)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 90)
                        .focused($timezoneFocused)
                        .onChange(of: timezoneFocused) { _, focused in
                            if !focused { timezone.markTouched() }
                        }
                } else {
                    TimezonePickerView(selectedTimezone: $timezone.value)
                }
                Spacer()
                Button {
                    state.useTimezonePicker.toggle()
                } label: {
                    Image(systemName: state.useTimezonePicker ? "keyboard" : "globe")
                        .padding(4)
                }
                .contentShape(Rectangle())
                .help(state.useTimezonePicker ? Strings.Workflow.typeManuallyHelp : Strings.Workflow.pickFromListHelp)
            }
            .fieldError(timezoneError, show: timezone.touched)
        }
        .padding(10)
    }

    private var archiveSourceOptions: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text(Strings.Workflow.sourceActionLabel)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Picker("", selection: $state.sourceAction) {
                    Text(Strings.Workflow.archiveOption).tag(SourceAction.archive)
                    Text(Strings.Workflow.deleteOption).tag(SourceAction.delete)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 220)
                HelpButton(Strings.Workflow.sourceActionHelp)
            }
            if state.sourceAction == .delete {
                Label(Strings.Workflow.deleteSourceWarning, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.yellow)
            }
        }
        .padding(10)
    }

    // MARK: - Execution

    private var executionBar: some View {
        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
            Divider().gridCellUnsizedAxes(.horizontal)
            GridRow {
                Text(Strings.Workflow.modeLabel).gridColumnAlignment(.trailing)
                HStack(spacing: 12) {
                    Picker("", selection: $state.applyMode) {
                        Text(Strings.Workflow.dryRunOption).tag(false)
                        Text(Strings.Workflow.applyOption).tag(true)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 160)

                    Button(state.isRunning ? Strings.Workflow.runningButton : Strings.Workflow.runButton) { runWorkflow() }
                        .disabled(
                            state.isRunning
                            || state.selectedProfile.isEmpty
                            || !state.allStepsReady
                            || !timezoneIsValid
                        )
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
        var path = readyDir + "/YYYY"
        if !state.group.isEmpty {
            var groupName = state.group
            if state.appendTimezoneToGroup && state.enabledSteps.contains(.fixTimezone) && !state.timezone.isEmpty {
                groupName += " (\(state.timezone))"
            }
            path += "/\(groupName)"
        }
        path += "/YYYY-MM-DD"
        return path
    }

    // MARK: - Actions

    private func countMediaFiles() -> Int {
        guard let profile = state.activeProfile else { return 0 }
        let extensions = (profile.fileExtensions ?? []).map {
            $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        }
        guard !extensions.isEmpty else { return 0 }
        let dir = state.sourceDir
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

        let (script, args) = state.buildPipelineArgs()

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
            sourceDir.value = url.path
            sourceDir.markTouched()
        }
    }

    private func pickReadyDir() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.readyDir = url.path
        }
    }
}
