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
        if tz.isEmpty { return true }
        let pattern = /^[+-]\d{4}$/
        return tz.contains(pattern)
    }

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 16) {
                profileSelector
                if !state.selectedProfile.isEmpty {
                    stepsPipeline
                    stepOptions
                    executionBar
                }
            }
            .padding()

            LogOutputView(lines: state.logOutput, onClear: { state.clearLog() })
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
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 2) {
                    ForEach(state.availableSteps) { step in
                        let isEnabled = state.enabledSteps.contains(step)
                        let isFirst = step == state.availableSteps.first
                        let isLast = step == state.availableSteps.last

                        Button {
                            if isEnabled {
                                state.enabledSteps.remove(step)
                            } else {
                                state.enabledSteps.insert(step)
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: step.systemImage)
                                    .font(.system(size: 10))
                                    .foregroundStyle(isEnabled ? step.iconColor : .tertiary)
                                Text(step.rawValue)
                                    .font(.system(size: 11, weight: .medium))
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(isEnabled ? step.iconColor.opacity(0.12) : .clear)
                            .foregroundStyle(isEnabled ? .primary : .tertiary)
                        }
                        .buttonStyle(.plain)
                        .clipShape(
                            UnevenRoundedRectangle(
                                topLeadingRadius: isFirst ? 6 : 0,
                                bottomLeadingRadius: isFirst ? 6 : 0,
                                bottomTrailingRadius: isLast ? 6 : 0,
                                topTrailingRadius: isLast ? 6 : 0
                            )
                        )
                        .overlay(
                            UnevenRoundedRectangle(
                                topLeadingRadius: isFirst ? 6 : 0,
                                bottomLeadingRadius: isFirst ? 6 : 0,
                                bottomTrailingRadius: isLast ? 6 : 0,
                                topTrailingRadius: isLast ? 6 : 0
                            )
                            .strokeBorder(isEnabled ? AnyShapeStyle(step.iconColor.opacity(0.4)) : AnyShapeStyle(.quaternary), lineWidth: 1)
                        )
                        .help(step.help)

                        if step != state.availableSteps.last {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 8))
                                .foregroundStyle(.quaternary)
                        }
                    }
                    Spacer()
                }

                Text(enabledStepsSummary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        } label: {
            Label("Pipeline", systemImage: "arrow.triangle.branch")
                .font(.headline)
                .foregroundStyle(Color.accentColor)
        }
    }

    private var enabledStepsSummary: String {
        let enabled = state.availableSteps.filter { state.enabledSteps.contains($0) }
        if enabled.isEmpty { return "No steps selected" }
        return enabled.map(\.help).joined(separator: " → ")
    }

    // MARK: - Step-specific options

    @ViewBuilder
    private var stepOptions: some View {
        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
            GridRow {
                HelpLabel("Subfolder", help: Strings.Workflow.subfolder)
                    .gridColumnAlignment(.trailing)
                TextField("Optional", text: $state.subfolder)
                    .textFieldStyle(.roundedBorder)
            }

            if state.enabledSteps.contains(.importFromCard) {
                GridRow {
                    HelpLabel("Source", help: Strings.Workflow.sourceDir)
                        .gridColumnAlignment(.trailing)
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
                }

                GridRow {
                    Text("")
                    HStack(spacing: 12) {
                        HStack(spacing: 4) {
                            Toggle(isOn: $state.skipCompanion) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Skip companion files")
                                    if !companionExtensions.isEmpty {
                                        Text(companionExtensions)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            HelpButton(Strings.Workflow.skipCompanion)
                        }

                        HStack(spacing: 4) {
                            Toggle("Preserve files on card", isOn: $state.preserveSource)
                            HelpButton(Strings.Workflow.preserveSource)
                        }
                    }
                }
            }

            if state.enabledSteps.contains(.fixTimezone) {
                GridRow {
                    Text("Timezone").gridColumnAlignment(.trailing)
                    HStack(spacing: 6) {
                        if !state.useTimezonePicker {
                            TextField("+HHMM", text: $state.timezone)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 90)
                                .foregroundColor(timezoneIsValid ? .primary : .red)
                            if !timezoneIsValid {
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
                        }
                        .help(state.useTimezonePicker ? "Type manually" : "Pick from list")
                    }
                }
            }
        }
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
                            || state.enabledSteps.isEmpty
                            || !timezoneIsValid
                        )
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)

                    if state.isRunning {
                        Button("Cancel", role: .destructive) { state.cancelRunning() }
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private let pipelineTaskNames: [PipelineStep: String] = [
        .tag: "tag",
        .fixTimezone: "fix-timestamp",
        .organize: "organize",
        .gyroflow: "gyroflow"
    ]

    private func countMediaFiles() -> Int {
        guard let profile = state.activeProfile else { return 0 }
        let extensions = (profile.fileExtensions ?? []).map {
            $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        }
        guard !extensions.isEmpty else { return 0 }
        let dir = state.enabledSteps.contains(.importFromCard) ? state.sourceDir : (profile.importDir ?? "")
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
        state.isRunning = true

        let steps = state.enabledSteps
        let hasImport = steps.contains(.importFromCard)

        let script = hasImport ? "import-media.sh" : "media-pipeline.sh"
        var args: [String] = []
        args += ["--profile", state.selectedProfile]
        if !state.subfolder.isEmpty { args += ["--group", state.subfolder] }
        if hasImport {
            if state.skipCompanion { args.append("--skip-companion") }
            if !state.sourceDir.isEmpty { args.append(state.sourceDir) }
        } else {
            let taskArgs = state.availableSteps
                .filter { $0 != .importFromCard && steps.contains($0) }
                .compactMap { pipelineTaskNames[$0] }
            if !taskArgs.isEmpty {
                args += ["--tasks"] + taskArgs
            }
        }
        if steps.contains(.fixTimezone) && !state.timezone.isEmpty {
            args += ["--timezone", state.timezone]
        }
        if state.applyMode { args.append("--apply") }

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
}
