import SwiftUI

struct ProfileEditingSession: Equatable {
    var name: String
    var profile: MediaProfile
}

struct ProfilesView: View {
    @Bindable var state: AppState
    @State private var selectedProfile: String?
    @State private var editor: ProfileEditingSession?
    @State private var snapshot: ProfileEditingSession?
    @State private var showDeleteConfirmation = false
    @State private var showDiscardConfirmation = false
    @State private var pendingAction: PendingAction?

    private enum PendingAction {
        case loadProfile(ProfileEditingSession)
        case switchTab(SidebarTab)
        case dismiss
    }

    private var isDirty: Bool {
        guard let editor, let snapshot else { return false }
        return editor != snapshot
    }

    private var sessionBinding: Binding<ProfileEditingSession> {
        Binding(
            get: { editor ?? ProfileEditingSession(name: "", profile: MediaProfile()) },
            set: { editor = $0 }
        )
    }

    var body: some View {
        HStack(spacing: 0) {
            profileList
                .frame(width: 200)

            Divider()

            if editor != nil {
                ProfileEditorView(
                    session: sessionBinding,
                    onSave: { saveCurrentProfile() },
                    onCancel: {
                        if isDirty {
                            pendingAction = .dismiss
                            showDiscardConfirmation = true
                        } else {
                            editor = nil
                            snapshot = nil
                            selectedProfile = nil
                        }
                    }
                )
                .frame(maxWidth: .infinity)
            } else {
                Text(Strings.Profiles.selectPrompt)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(Strings.Nav.mediaProfiles)
        .onChange(of: state.selectedTab) { oldValue, newValue in
            if oldValue == .profiles && newValue != .profiles && isDirty {
                state.selectedTab = .profiles
                pendingAction = .switchTab(newValue)
                showDiscardConfirmation = true
            }
        }
        .confirmationDialog(
            Strings.Profiles.unsavedChangesTitle,
            isPresented: $showDiscardConfirmation
        ) {
            Button(Strings.Profiles.saveAndContinue) {
                saveCurrentProfile()
                resolvePendingAction()
            }
            Button(Strings.Profiles.discardChanges, role: .destructive) {
                editor = snapshot
                resolvePendingAction()
            }
            Button(Strings.Common.cancel, role: .cancel) {
                pendingAction = nil
            }
        } message: {
            Text(Strings.Profiles.unsavedChangesMessage)
        }
    }

    private var profileList: some View {
        VStack(spacing: 0) {
            List(selection: $selectedProfile) {
                ForEach(state.sortedProfileNames, id: \.self) { name in
                    HStack(spacing: 6) {
                        if let profile = state.profile(named: name) {
                            Image(
                                systemName: profile.type?.systemImage
                                    ?? "questionmark"
                            )
                            .foregroundStyle(.secondary)
                            .frame(width: 14)

                            let device = [
                                profile.exif?.make, profile.exif?.model,
                            ]
                            .compactMap { $0 }.joined(separator: " ")
                            VStack(alignment: .leading, spacing: 2) {
                                if !device.isEmpty {
                                    Text(device).fontWeight(.medium)
                                    Text(name)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                } else {
                                    Text(name).fontWeight(.medium)
                                }
                            }
                        } else {
                            Text(name).fontWeight(.medium)
                        }
                        Spacer()
                    }
                    .tag(name)
                }
            }
            .onChange(of: selectedProfile) { _, newValue in
                guard pendingAction == nil else { return }
                guard let name = newValue, name != snapshot?.name else { return }
                guard let profile = state.profile(named: name) else { return }
                requestProfileLoad(
                    ProfileEditingSession(name: name, profile: profile)
                )
            }

            Divider()
            HStack {
                Button {
                    requestProfileLoad(
                        ProfileEditingSession(
                            name: "new-profile", profile: MediaProfile()
                        )
                    )
                } label: {
                    Image(systemName: "plus")
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)

                Button {
                    showDeleteConfirmation = true
                } label: {
                    Image(systemName: "minus")
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)
                .disabled(selectedProfile == nil)
                .confirmationDialog(
                    Strings.Profiles.deleteConfirmationTitle(
                        selectedProfile ?? ""
                    ),
                    isPresented: $showDeleteConfirmation,
                    titleVisibility: .visible
                ) {
                    Button(Strings.Common.delete, role: .destructive) {
                        if let name = selectedProfile {
                            deleteProfile(name)
                        }
                    }
                } message: {
                    Text(Strings.Profiles.deleteConfirmationMessage)
                }

                Button {
                    duplicateProfile()
                } label: {
                    Image(systemName: "doc.on.doc")
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)
                .disabled(selectedProfile == nil)

                Spacer()
            }
            .padding(6)
        }
    }

    // MARK: - Profile transitions

    private func requestProfileLoad(_ target: ProfileEditingSession) {
        if isDirty {
            pendingAction = .loadProfile(target)
            selectedProfile = snapshot?.name
            showDiscardConfirmation = true
        } else {
            applyProfileLoad(target)
        }
    }

    private func applyProfileLoad(_ target: ProfileEditingSession) {
        var session = target
        if session.profile.type == nil { session.profile.type = .video }
        editor = session
        snapshot = session
        selectedProfile = session.name
    }

    private func resolvePendingAction() {
        guard let action = pendingAction else { return }
        pendingAction = nil
        switch action {
        case .loadProfile(let target):
            applyProfileLoad(target)
        case .switchTab(let tab):
            state.selectedTab = tab
        case .dismiss:
            editor = nil
            snapshot = nil
            selectedProfile = nil
        }
    }

    // MARK: - CRUD

    private func saveCurrentProfile() {
        guard let editor, state.profilesConfig != nil else { return }

        if let snapshot, snapshot.name != editor.name {
            state.profilesConfig?.profiles.removeValue(forKey: snapshot.name)
            if state.workflowSession.profileName == snapshot.name {
                state.workflowSession.profileName = editor.name
            }
        }
        state.profilesConfig?.profiles[editor.name] = editor.profile

        writeProfiles()
        snapshot = editor
        selectedProfile = editor.name
    }

    private func deleteProfile(_ name: String) {
        state.profilesConfig?.profiles.removeValue(forKey: name)
        writeProfiles()
        if state.workflowSession.profileName == name {
            state.workflowSession = WorkflowSession()
        }
        selectedProfile = nil
        editor = nil
        snapshot = nil
    }

    private func duplicateProfile() {
        guard let name = selectedProfile,
            let profile = state.profile(named: name)
        else { return }

        let baseName = name.replacing(/\ copy \d+$/, with: "")
        var counter = 1
        var duplicateName = "\(baseName) copy \(counter)"
        while state.profile(named: duplicateName) != nil {
            counter += 1
            duplicateName = "\(baseName) copy \(counter)"
        }
        requestProfileLoad(
            ProfileEditingSession(name: duplicateName, profile: profile)
        )
    }

    private func writeProfiles() {
        guard let config = state.profilesConfig else { return }
        do {
            try ProfileService.write(config, to: state.resolvedProfilesPath)
        } catch {
            state.profileLoadError = ProfileLoadError(
                message: Strings.Errors.profilesWriteFailed,
                filePath: state.resolvedProfilesPath,
                detail: error.localizedDescription
            )
        }
    }
}

struct ProfileEditorView: View {
    @Binding var session: ProfileEditingSession
    let onSave: () -> Void
    let onCancel: () -> Void

    var body: some View {
        ScrollView {
            Grid(
                alignment: .leadingFirstTextBaseline,
                horizontalSpacing: 12,
                verticalSpacing: 10
            ) {
                GridRow {
                    Text(Strings.Profiles.nameLabel).gridColumnAlignment(
                        .trailing
                    )
                    TextField(
                        Strings.Profiles.namePlaceholder,
                        text: $session.name
                    )
                    .textFieldStyle(.roundedBorder)
                }

                GridRow {
                    HelpLabel(
                        Strings.Profiles.typeLabel,
                        help: Strings.Profiles.typeHelp
                    )
                    Picker("", selection: typeBinding) {
                        Text(Strings.Profiles.videoOption).tag(MediaType.video)
                        Text(Strings.Profiles.photoOption).tag(MediaType.photo)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 160)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text(Strings.Profiles.sourceDirLabel)
                    dirField($session.profile.sourceDir)
                }
                GridRow {
                    Text(Strings.Profiles.readyDirLabel)
                    dirField($session.profile.readyDir)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text(Strings.Profiles.exifMakeLabel)
                    TextField(
                        Strings.Profiles.exifMakePlaceholder,
                        text: exifBinding(\.make)
                    )
                    .textFieldStyle(.roundedBorder)
                }
                GridRow {
                    Text(Strings.Profiles.exifModelLabel)
                    TextField(
                        Strings.Profiles.exifModelPlaceholder,
                        text: exifBinding(\.model)
                    )
                    .textFieldStyle(.roundedBorder)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    HelpLabel(
                        Strings.Profiles.fileTypesLabel,
                        help: Strings.Profiles.fileExtensionsHelp
                    )
                    ExtensionField(items: $session.profile.fileExtensions)
                }

                GridRow {
                    HelpLabel(
                        Strings.Profiles.companionLabel,
                        help: Strings.Profiles.companionHelp
                    )
                    ExtensionField(items: $session.profile.companionExtensions)
                }

                GridRow {
                    HelpLabel(
                        Strings.Profiles.tagsLabel,
                        help: Strings.Profiles.tagsHelp
                    )
                    CommaSeparatedField(
                        items: $session.profile.tags,
                        placeholder: Strings.Profiles.tagPlaceholder
                    )
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text("")
                    HStack(spacing: 4) {
                        Toggle(
                            Strings.Profiles.gyroflowToggle,
                            isOn: gyroflowToggle
                        )
                        HelpButton(Strings.Profiles.gyroflowHelp)
                    }
                }
            }
            .padding()
        }
        .safeAreaInset(edge: .bottom) {
            HStack {
                Spacer()
                Button(Strings.Common.cancel) { onCancel() }
                    .keyboardShortcut(.escape)
                Button(Strings.Profiles.saveButton) { onSave() }
                    .keyboardShortcut(.return, modifiers: .command)
                    .buttonStyle(.borderedProminent)
                    .disabled(session.name.isEmpty)
            }
            .padding()
            .background(.bar)
        }
    }

    private func dirField(_ binding: Binding<String?>) -> some View {
        HStack(spacing: 6) {
            TextField("", text: optionalBinding(binding))
                .textFieldStyle(.roundedBorder)
            Button(Strings.Common.browse) {
                let panel = NSOpenPanel()
                panel.canChooseDirectories = true
                panel.canChooseFiles = false
                if panel.runModal() == .OK, let url = panel.url {
                    binding.wrappedValue = url.path
                }
            }
            .controlSize(.small)
        }
    }

    private func optionalBinding(_ binding: Binding<String?>) -> Binding<String>
    {
        Binding(
            get: { binding.wrappedValue ?? "" },
            set: { binding.wrappedValue = $0.isEmpty ? nil : $0 }
        )
    }

    private func exifBinding(_ sub: WritableKeyPath<ExifConfig, String?>)
        -> Binding<String>
    {
        Binding(
            get: { session.profile.exif?[keyPath: sub] ?? "" },
            set: { newValue in
                if session.profile.exif == nil {
                    session.profile.exif = ExifConfig()
                }
                session.profile.exif?[keyPath: sub] =
                    newValue.isEmpty ? nil : newValue
            }
        )
    }

    private var typeBinding: Binding<MediaType> {
        Binding(
            get: { session.profile.type ?? .video },
            set: { session.profile.type = $0 }
        )
    }

    private var gyroflowToggle: Binding<Bool> {
        Binding(
            get: { session.profile.gyroflowEnabled ?? false },
            set: { session.profile.gyroflowEnabled = $0 }
        )
    }
}

// MARK: - Help components

struct HelpLabel: View {
    let text: String
    let help: String
    @State private var showHelp = false

    init(_ text: String, help: String) {
        self.text = text
        self.help = help
    }

    var body: some View {
        HStack(spacing: 4) {
            Text(text)
            HelpButton(help)
        }
    }
}

struct HelpButton: View {
    let text: String
    @State private var showHelp = false

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Image(systemName: "questionmark.circle")
            .foregroundStyle(.secondary)
            .onTapGesture { showHelp.toggle() }
            .popover(isPresented: $showHelp, arrowEdge: .bottom) {
                Text(text)
                    .font(.caption)
                    .padding(10)
                    .frame(width: 240, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
    }
}
