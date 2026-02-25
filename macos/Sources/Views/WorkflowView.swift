import SwiftUI

struct WorkflowView: View {
    @Bindable var state: AppState
    @State private var sourceDirError: String?
    @FocusState private var sourceDirFocused: Bool
    @State private var showUpgradeSheet = false
    @State private var detectedFileCount = 0
    private var licenseStore: LicenseStore { LicenseStore.shared }

    private var companionExtensions: String {
        state.activeProfile?.companionExtensions?.joined(separator: ", ") ?? ""
    }

    private var timezoneIsValid: Bool {
        let tz = state.timezone
        if tz.isEmpty {
            return !state.enabledSteps.contains(.fixTimezone)
        }
        let pattern = /^[+-]\d{4}$/
        return tz.contains(pattern)
    }

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
        .navigationTitle("Workflow")
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
                            Button("Reveal in Finder") {
                                NSWorkspace.shared.selectFile(error.filePath, inFileViewerRootedAtPath: "")
                            }
                            .controlSize(.small)
                        }
                    }
                }
            }

            GridRow {
                Text("Profile").gridColumnAlignment(.trailing)
                ProfilePicker(selection: $state.selectedProfile, state: state)
                    .onChange(of: state.selectedProfile) { _, newValue in
                        state.resetWorkflowFields(for: newValue)
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
                Text(step.rawValue)
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
                    TextField("SD card or directory path", text: $state.sourceDir)
                        .textFieldStyle(.roundedBorder)
                        .focused($sourceDirFocused)
                        .onChange(of: sourceDirFocused) { _, focused in
                            if !focused { validateSourceDir() }
                        }
                        .onChange(of: state.sourceDir) { _, _ in
                            sourceDirError = nil
                        }
                    Button("Browse...") { pickSourceDir() }
                        .controlSize(.small)
                }
                if let error = sourceDirError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }

            HStack(spacing: 4) {
                Toggle(isOn: $state.copyCompanionFiles) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Copy companion files")
                        if companionExtensions.isEmpty {
                            Text("No companion files noted for this device")
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
                HelpButton(Strings.Workflow.copyCompanionFiles)
            }
        }
        .padding(10)
    }

    private var tagOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text("Tags:")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)
                TextField("tag1, tag2", text: $state.tags)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
            }
            HStack(spacing: 4) {
                Text("Camera:")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)
                TextField("Make", text: $state.exifMake)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                TextField("Model", text: $state.exifModel)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
            }
        }
        .padding(10)
    }

    private var organizeOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TextField("Ready directory path", text: $state.readyDir)
                    .textFieldStyle(.roundedBorder)
                Button("Browse...") { pickReadyDir() }
                    .controlSize(.small)
            }
            Text(state.readyDir.isEmpty ? "Set ready directory above" : destinationPreview(readyDir: state.readyDir))
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 4) {
                HelpLabel("Group", help: Strings.Workflow.group)
                TextField("Optional", text: $state.group)
                    .textFieldStyle(.roundedBorder)
            }
            if state.enabledSteps.contains(.fixTimezone) {
                HStack(spacing: 4) {
                    Toggle("Append timezone to group folder", isOn: $state.appendTimezoneToGroup)
                        .disabled(state.group.isEmpty)
                    HelpButton(Strings.Workflow.appendTimezoneToGroup)
                }
            }
        }
        .padding(10)
    }

    private var fixTimezoneOptions: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if !state.useTimezonePicker {
                    TextField("+HHMM", text: $state.timezone)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 90)
                        .foregroundColor(timezoneIsValid ? .primary : .red)
                    if !state.timezone.isEmpty && !timezoneIsValid {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.yellow)
                            .help("Expected format: +HHMM or -HHMM")
                    }
                } else {
                    TimezonePickerView(selectedTimezone: $state.timezone)
                }
                Spacer()
                Button {
                    state.useTimezonePicker.toggle()
                } label: {
                    Image(systemName: state.useTimezonePicker ? "keyboard" : "globe")
                        .padding(4)
                }
                .contentShape(Rectangle())
                .help(state.useTimezonePicker ? "Type manually" : "Pick from list")
            }
            if state.timezone.isEmpty {
                Label("Timezone required", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.yellow)
            }
        }
        .padding(10)
    }

    private var archiveSourceOptions: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text("Source action:")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Picker("", selection: $state.sourceAction) {
                    Text("Archive").tag(SourceAction.archive)
                    Text("Delete").tag(SourceAction.delete)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 220)
                HelpButton(Strings.Workflow.sourceAction)
            }
            if state.sourceAction == .delete {
                Label("Deletes processed files and companions from source after successful processing", systemImage: "exclamationmark.triangle.fill")
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
                Text("Mode").gridColumnAlignment(.trailing)
                HStack(spacing: 12) {
                    Picker("", selection: $state.applyMode) {
                        Text("Dry Run").tag(false)
                        Text("Apply").tag(true)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 160)

                    Button(state.isRunning ? "Running..." : "Run") { runWorkflow() }
                        .disabled(
                            state.isRunning
                            || state.selectedProfile.isEmpty
                            || !state.allStepsReady
                            || !timezoneIsValid
                        )
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)

                    if state.isRunning {
                        Button("Cancel", role: .destructive) { state.cancelRunning() }
                    }

                    Spacer()

                    Button {
                        state.showLog.toggle()
                    } label: {
                        Image(systemName: "terminal")
                            .foregroundStyle(state.showLog ? .primary : .secondary)
                    }
                    .buttonStyle(.borderless)
                    .help(state.showLog ? "Hide log" : "Show log")
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

    private func validateSourceDir() {
        let path = state.sourceDir
        guard !path.isEmpty else { sourceDirError = nil; return }
        var isDir: ObjCBool = false
        if !FileManager.default.fileExists(atPath: path, isDirectory: &isDir) {
            sourceDirError = "Directory not found"
        } else if !isDir.boolValue {
            sourceDirError = "Path is a file, not a directory"
        } else {
            sourceDirError = nil
        }
    }

    private func pickSourceDir() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.sourceDir = url.path
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
