import SwiftUI

/// Check a card against the backup locations before it is wiped. Laid out like
/// Workflow: the card's folder, one row per backup location with a toggle to include
/// it, the options, and Verify. The check is read-only, so there is no dry run.
struct VerifyView: View {
    @Bindable var state: AppState
    @State private var editingLocations = false

    private var session: Binding<VerifySession> { $state.verifySession }

    var body: some View {
        // The same frame as Workflow: the form at its own width, and once a check has
        // started, the results panel beside it, which widens the window as it opens.
        HStack(alignment: .top, spacing: 0) {
            form
                .frame(width: WorkflowView.formWidth)
                .frame(maxHeight: .infinity, alignment: .top)
            if state.verifySession.showsResults {
                Divider()
                VerifyResultsPanel(state: state)
                    .frame(maxWidth: WorkflowDetail.panelMaxWidth)
            }
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
                ToggleRow(title: Strings.Verify.showMatched, isOn: session.showMatched)
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
