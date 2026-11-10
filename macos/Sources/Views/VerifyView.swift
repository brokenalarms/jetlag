import SwiftUI

/// Check a card against the backup locations before it is wiped. Laid out like
/// Workflow: the card's folder, one row per backup location with a toggle to include
/// it, the options, and Verify. The check is read-only, so there is no dry run.
struct VerifyView: View {
    @Bindable var state: AppState
    @State private var editingLocations = false

    private var session: Binding<VerifySession> { $state.verifySession }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            form
                .frame(width: Theme.Size.form)
                .frame(maxHeight: .infinity, alignment: .top)
            Divider()
            VerifyResults(state: state)
                .frame(minWidth: Theme.Size.verifyResultsMin, maxWidth: WorkflowDetail.panelMaxWidth)
        }
        .sheet(isPresented: $editingLocations) {
            BackupLocationsEditor(state: state, isPresented: $editingLocations)
        }
        .onAppear {
            // "Include companion files" starts as the workflow's copy-companion choice.
            if state.verifySession.report == VerifyReport(), !state.verifySession.isRunning {
                state.verifySession.includeCompanions = state.workflowSession.copyCompanionFiles
            }
        }
    }

    private var form: some View {
        Form {
            Section(Strings.Verify.sourceSection) {
                PathField(placeholder: Strings.Verify.sourcePlaceholder,
                          path: session.source, error: nil, help: Strings.Verify.sourceHelp)
            }

            Section {
                let backups = state.profilesConfig?.sortedBackups ?? []
                if backups.isEmpty {
                    Text(Strings.Verify.noLocations)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Text.secondary)
                }
                ForEach(backups) { location in
                    BackupLocationRow(name: location.name, config: location.config,
                                      isOn: enabledBinding(location.name))
                }
            } header: {
                HStack {
                    Text(Strings.Verify.locationsSection)
                    Spacer()
                    Button(Strings.Verify.editLocations) { editingLocations = true }
                        .buttonStyle(.link)
                }
            }

            Section(Strings.Verify.optionsSection) {
                ToggleRow(title: Strings.Verify.includeCompanions,
                          caption: Strings.Verify.includeCompanionsCaption,
                          isOn: session.includeCompanions)
                ToggleRow(title: Strings.Verify.verifyHashes,
                          caption: Strings.Verify.verifyHashesCaption,
                          isOn: session.verifyHashes)
                ToggleRow(title: Strings.Verify.includeNetwork,
                          isOn: session.includeNetwork,
                          isEnabled: state.verifySession.verifyHashes)
            }

            Section {
                HStack {
                    Spacer()
                    if state.verifySession.isRunning {
                        ProgressView().controlSize(.small)
                        Button(Strings.Verify.stopButton) { state.cancelVerify() }
                    } else {
                        Button(Strings.Verify.runButton) { state.runVerify() }
                            .keyboardShortcut(.defaultAction)
                            .disabled(!state.canRunVerify)
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    private func enabledBinding(_ name: String) -> Binding<Bool> {
        Binding(
            get: { state.verifySession.enabledLocations.contains(name) },
            set: { isOn in
                if isOn {
                    state.verifySession.enabledLocations.insert(name)
                } else {
                    state.verifySession.enabledLocations.remove(name)
                }
            })
    }
}

/// A backup location: its toggle, its name, its folder and a Local or Network label.
/// The label is information only: it says which hash checkbox covers the location.
struct BackupLocationRow: View {
    let name: String
    let config: BackupLocationConfig
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            VStack(alignment: .leading, spacing: Theme.Space.xxs) {
                HStack(spacing: Theme.Space.md) {
                    Text(name)
                    Text(config.isNetwork ? Strings.Verify.network : Strings.Verify.local)
                        .font(Theme.Typography.chip)
                        .foregroundStyle(Theme.Text.secondary)
                }
                Text(config.path)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Text.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
    }
}

/// The check's outcome: a summary line that is always shown once a check has run, so
/// an empty list reads as all clear rather than as a check that found nothing, then a
/// row per file that needs attention, with one status per enabled location.
struct VerifyResults: View {
    @Bindable var state: AppState

    private var report: VerifyReport { state.verifySession.report }
    private var locationNames: [String] { report.locations.map(\.location) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Space.sm) {
                    let rows = report.visibleRows(showMatched: state.verifySession.showMatched)
                    if rows.isEmpty, report.summary != nil {
                        Label(Strings.Verify.allClear, systemImage: "checkmark.circle")
                            .foregroundStyle(Theme.Status.success)
                    }
                    ForEach(rows) { row in
                        VerifyRowView(row: row, locationNames: locationNames)
                        Divider()
                    }
                    ForEach(state.verifySession.log.filter { $0.stream == .stderr }) { line in
                        Text(line.strippedText)
                            .font(Theme.Typography.captionMono)
                            .foregroundStyle(Theme.Text.secondary)
                    }
                }
                .padding(Theme.Space.xl)
            }
        }
    }

    private var header: some View {
        HStack(spacing: Theme.Space.lg) {
            if let summary = report.summary {
                Text(Strings.Verify.summary(
                    checked: summary.checked, onEvery: summary.onEveryLocation,
                    attention: summary.needAttention, notChecked: summary.notChecked,
                    kinds: summary.notCheckedKinds))
                    .font(Theme.Typography.subheadline)
            } else if state.verifySession.isRunning {
                ProgressView().controlSize(.small)
            }
            Spacer()
            Toggle(Strings.Verify.showMatched, isOn: $state.verifySession.showMatched)
                .toggleStyle(.checkbox)
        }
        .padding(Theme.Space.xl)
    }
}

/// One card file: its path, then each location's verdict.
struct VerifyRowView: View {
    let row: VerifyRow
    let locationNames: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.xs) {
            Text(row.file)
                .font(Theme.Typography.fileMono)
                .textSelection(.enabled)
            HStack(spacing: Theme.Space.xxl) {
                ForEach(locationNames, id: \.self) { name in
                    if let outcome = row.outcomes[name] {
                        VerifyOutcomeBadge(location: name, outcome: outcome)
                    }
                }
            }
            let details = Strings.Verify.clipDetails(row.details)
            if !details.isEmpty {
                Text(details)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(row.details.opens == false ? Theme.Status.failure : Theme.Text.secondaryColor)
            }
            if row.details.recordedHashesDisagree {
                Text(Strings.Verify.recordedHashesDisagree)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Status.warning)
            }
        }
    }
}

struct VerifyOutcomeBadge: View {
    let location: String
    let outcome: VerifyOutcome

    var body: some View {
        HStack(spacing: Theme.Space.sm) {
            Image(systemName: outcome.verdict.passes ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(outcome.verdict.passes ? Theme.Status.success : Theme.Status.warning)
            Text("\(location): \(outcome.verdict.label)")
                .font(Theme.Typography.file)
            if let hash = outcome.hash, hash != "mismatch" {
                Text(hash == "match" ? Strings.Verify.hashMatch : Strings.Verify.hashNotHashable)
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.secondary)
            }
        }
        .help(outcome.copies.joined(separator: "\n"))
    }
}

/// The backup-location configuration: any number of locations, each a name and a
/// root folder (or host:/path). Saved to the profiles file's `backups:` mapping.
struct BackupLocationsEditor: View {
    @Bindable var state: AppState
    @Binding var isPresented: Bool

    private struct Draft: Identifiable {
        let id = UUID()
        var name: String
        var path: String
    }

    @State private var drafts: [Draft] = []

    private var namesAreUnique: Bool {
        let names = drafts.map { $0.name.trimmingCharacters(in: .whitespaces) }
        return Set(names).count == names.count
    }

    private var canSave: Bool {
        namesAreUnique && drafts.allSatisfy {
            !$0.name.trimmingCharacters(in: .whitespaces).isEmpty
                && !$0.path.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.xl) {
            Text(Strings.Verify.locationsSection)
                .font(Theme.Typography.title)
            ForEach($drafts) { $draft in
                HStack(alignment: .top, spacing: Theme.Space.lg) {
                    TextField(Strings.Verify.locationNamePlaceholder, text: $draft.name)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: Theme.Size.typePicker)
                    PathField(placeholder: Strings.Verify.locationPathPlaceholder,
                              path: $draft.path, error: nil)
                    Button(Strings.Verify.removeLocation) {
                        drafts.removeAll { $0.id == draft.id }
                    }
                    .controlSize(.small)
                }
            }
            if !namesAreUnique {
                Text(Strings.Verify.duplicateLocationName)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Status.failure)
            }
            HStack {
                Button(Strings.Verify.addLocation) { drafts.append(Draft(name: "", path: "")) }
                Spacer()
                Button(Strings.Common.cancel) { isPresented = false }
                    .keyboardShortcut(.cancelAction)
                Button(Strings.Verify.saveLocations) { save() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canSave)
            }
        }
        .padding(Theme.Space.page)
        .frame(width: Theme.Size.form)
        .onAppear {
            drafts = (state.profilesConfig?.sortedBackups ?? []).map {
                Draft(name: $0.name, path: $0.config.path)
            }
        }
    }

    private func save() {
        var backups: [String: BackupLocationConfig] = [:]
        for draft in drafts {
            backups[draft.name.trimmingCharacters(in: .whitespaces)] =
                BackupLocationConfig(path: draft.path.trimmingCharacters(in: .whitespaces))
        }
        state.saveBackups(backups)
        isPresented = false
    }
}
