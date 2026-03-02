import SwiftUI

struct WorkflowView: View {
    @Bindable var state: AppState
    @State private var showUpgradeSheet = false
    @State private var detectedFileCount = 0
    @State private var showGyroflowDeps = false
    @State private var gyroflowToolStatus: WorkflowSession.GyroflowToolStatus?
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
        .inspector(isPresented: $state.showInspector) {
            VStack(spacing: 0) {
                if !state.visibleRows.isEmpty || state.isRunning {
                    DiffTableView(rows: state.visibleRows)
                } else if !state.showLogOutput {
                    Spacer()
                    Text(Strings.Workflow.inspectorEmptyLabel)
                        .font(.subheadline)
                        .foregroundStyle(.tertiary)
                    Spacer()
                }

                if state.showLogOutput {
                    LogOutputView(lines: state.logOutput, onClear: { state.clearLog() })
                }

                inspectorBottomBar
            }
            .inspectorColumnWidth(min: 480, ideal: defaultColumnWidth)
        }
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
        .alert(
            Strings.Workflow.timezoneConflictTitle,
            isPresented: $state.workflowSession.showTimezoneConflict
        ) {
            Button(Strings.Workflow.forceTimezoneButton, role: .destructive) {
                if state.workflowSession.timezoneConflictType == "mixed_timezones" {
                    state.workflowSession.allowMixedTimezones = true
                } else {
                    state.workflowSession.forceTimezone = true
                }
                state.workflowSession.showTimezoneConflict = false
                runWorkflow()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                state.workflowSession.showTimezoneConflict = false
            }
        } message: {
            Text(timezoneConflictMessage)
        }
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
//                    .windowResizeBehavior(.automatic)
                stepCard(step)
                if index < steps.count - 1 {
                    stepArrow
                }
            }
        }
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
        .popover(isPresented: step == .gyroflow ? $showGyroflowDeps : .constant(false), arrowEdge: .trailing) {
            if let status = gyroflowToolStatus {
                gyroflowDepsContent(status)
            }
        }
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
                    if step == .gyroflow {
                        let status = WorkflowSession.checkGyroflowTools(
                            gyroflowConfig: state.profilesConfig?.gyroflow
                        )
                        if status.anyMissing {
                            gyroflowToolStatus = status
                            showGyroflowDeps = true
                        }
                    }
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
        case .fixTimestamps:
            Divider()
            fixTimestampsOptions
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
            if session.enabledSteps.contains(.fixTimestamps) {
                HStack(spacing: 4) {
                    Toggle(Strings.Workflow.appendTimezoneToggle, isOn: $session.appendTimezoneToGroup)
                        .disabled(session.group.isEmpty)
                    HelpButton(Strings.Workflow.appendTimezoneHelp)
                }
            }
        }
        .padding(10)
    }

    private var fixTimestampsOptions: some View {
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

            HStack(spacing: 4) {
                Text(Strings.Workflow.timestampSourceLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                let parseable = hasParseableFilenames()
                Picker("", selection: $session.inferFromFilenames) {
                    Text(Strings.Workflow.timestampSourceMetadata).tag(false)
                    Text(Strings.Workflow.timestampSourceFilenames).tag(true)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 220)
                .disabled(!parseable)
                .onChange(of: parseable) { _, newValue in
                    if !newValue && session.inferFromFilenames {
                        session.inferFromFilenames = false
                    }
                }
            }

            HStack(spacing: 4) {
                HelpLabel(Strings.Workflow.timeOffsetLabel, help: Strings.Workflow.timeOffsetHelp)
                TextField(Strings.Workflow.timeOffsetPlaceholder, value: $session.timeOffsetSeconds, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 90)
            }

            HStack(spacing: 4) {
                Toggle(Strings.Workflow.updateFilenameDatesToggle, isOn: $session.updateFilenameDates)
                HelpButton(Strings.Workflow.updateFilenameDatesHelp)
            }

            if let preview = fixTimestampPreview {
                Text(preview)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(10)
    }

    private var fixTimestampPreview: String? {
        let session = state.workflowSession
        guard session.enabledSteps.contains(.fixTimestamps) else { return nil }

        var parts: [String] = []
        if session.inferFromFilenames {
            parts.append("Use filename dates as timestamp source")
        }
        if let offset = session.timeOffsetSeconds, offset != 0 {
            let sign = offset > 0 ? "+" : ""
            parts.append("Shift timestamps by \(sign)\(offset)s")
        }
        if !session.timezone.current.isEmpty && !session.inferFromFilenames {
            parts.append("Apply timezone \(session.timezone.current)")
        }
        if session.updateFilenameDates {
            parts.append("Rename files to match corrected dates")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
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

    // MARK: - Gyroflow dependency popup

    private func gyroflowDepsContent(_ status: WorkflowSession.GyroflowToolStatus) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(Strings.Workflow.gyroflowDepsTitle, systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(.yellow)

            Text(Strings.Workflow.gyroflowDepsMessage)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 6) {
                Text(Strings.Workflow.gyroflowDepsBrewPreamble)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Text(Strings.Workflow.gyroflowDepsBrewInstall)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary)
                    .clipShape(RoundedRectangle(cornerRadius: 4))

                if status.ffprobeMissing {
                    Label("ffprobe missing", systemImage: "xmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.yellow)
                }
                Text(Strings.Workflow.gyroflowDepsFfprobe)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary)
                    .clipShape(RoundedRectangle(cornerRadius: 4))

                if status.gyroflowMissing {
                    Label("gyroflow missing", systemImage: "xmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.yellow)
                }
                Text(Strings.Workflow.gyroflowDepsGyroflow)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
            }

            Button(Strings.Workflow.gyroflowDepsCopy) {
                var commands: [String] = []
                commands.append(Strings.Workflow.gyroflowDepsBrewInstall)
                if status.ffprobeMissing {
                    commands.append(Strings.Workflow.gyroflowDepsFfprobe)
                }
                if status.gyroflowMissing {
                    commands.append(Strings.Workflow.gyroflowDepsGyroflow)
                }
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(commands.joined(separator: "\n"), forType: .string)
            }
            .controlSize(.small)
        }
        .padding(12)
        .frame(width: 380)
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
                    .onChange(of: session.applyMode) { _, _ in
                        state.clearLog()
                    }

                    Button(state.isRunning ? Strings.Workflow.runningButton : Strings.Workflow.runButton) { runWorkflow() }
                        .disabled(state.isRunning || !session.allStepsReady)
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)

                    if state.isRunning {
                        Button(Strings.Common.cancel, role: .destructive) { state.cancelRunning() }
                    }

                    Spacer()
                }
            }
        }
    }

    // MARK: - Inspector bars

    private var inspectorBottomBar: some View {
        HStack {
            Button {
                withAnimation { state.showLogOutput.toggle() }
            } label: {
                Image(systemName: "terminal")
                    .foregroundStyle(state.showLogOutput ? .primary : .secondary)
            }
            .buttonStyle(.borderless)
            .help(state.showLogOutput ? Strings.Workflow.hideLogOutputHelp : Strings.Workflow.showLogOutputHelp)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Helpers

    private func destinationPreview(readyDir: String) -> String {
        let session = state.workflowSession
        var path = readyDir + "/YYYY"
        if !session.group.isEmpty {
            var groupName = session.group
            if session.appendTimezoneToGroup && session.enabledSteps.contains(.fixTimestamps) && !session.timezone.current.isEmpty {
                groupName += " (\(session.timezone.current))"
            }
            path += "/\(groupName)"
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
        let fileCount = countMediaFiles()
        if fileCount > licenseStore.fileLimit {
            detectedFileCount = fileCount
            showUpgradeSheet = true
            return
        }

        state.clearLog()
        state.showInspector = true
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
