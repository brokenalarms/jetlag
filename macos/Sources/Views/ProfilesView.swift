import SwiftUI

struct ProfilesView: View {
    @Bindable var state: AppState
    @State private var selectedProfile: String?
    @State private var editingName: String = ""
    @State private var editingProfile: MediaProfile?
    @State private var originalSnapshot: (name: String, profile: MediaProfile)?
    @State private var showDeleteConfirmation = false
    @State private var showDiscardConfirmation = false
    @State private var pendingSelection: String?
    @State private var pendingTabChange: SidebarTab?

    private var isDirty: Bool {
        guard let snapshot = originalSnapshot, let current = editingProfile
        else { return false }
        if state.profile(named: snapshot.name) == nil {
            return true
        }
        return editingName != snapshot.name || current != snapshot.profile
    }

    private var editingProfileBinding: Binding<MediaProfile> {
        Binding(
            get: { editingProfile ?? MediaProfile() },
            set: { editingProfile = $0 }
        )
    }

    var body: some View {
        HStack(spacing: 0) {
            profileList
                .frame(width: 200)

            Divider()

            if editingProfile != nil {
                ProfileEditorView(
                    profileName: $editingName,
                    profile: editingProfileBinding,
                    onSave: { saveCurrentProfile() },
                    onCancel: {
                        editingProfile = nil
                        editingName = ""
                        originalSnapshot = nil
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
                pendingTabChange = newValue
                showDiscardConfirmation = true
            }
        }
        .confirmationDialog(
            Strings.Profiles.unsavedChangesTitle,
            isPresented: $showDiscardConfirmation
        ) {
            Button(Strings.Profiles.saveAndContinue) {
                saveCurrentProfile()
                if let tab = pendingTabChange {
                    pendingTabChange = nil
                    state.selectedTab = tab
                } else if let pending = pendingSelection {
                    pendingSelection = nil
                    loadProfileForEditing(
                        pending,
                        state.profile(named: pending)
                    )
                }
            }
            Button(Strings.Profiles.discardChanges, role: .destructive) {
                if let snapshot = originalSnapshot {
                    editingName = snapshot.name
                    editingProfile = snapshot.profile
                }
                if let tab = pendingTabChange {
                    pendingTabChange = nil
                    state.selectedTab = tab
                } else if let pending = pendingSelection {
                    pendingSelection = nil
                    loadProfileForEditing(
                        pending,
                        state.profile(named: pending)
                    )
                }
            }
            Button(Strings.Common.cancel, role: .cancel) {
                pendingTabChange = nil
                pendingSelection = nil
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
            .onChange(of: selectedProfile) { oldValue, newValue in
                if pendingSelection != nil { return }

                if isDirty {
                    pendingSelection = newValue
                    selectedProfile = oldValue
                    showDiscardConfirmation = true
                } else if let name = newValue {
                    loadProfileForEditing(name, state.profile(named: name))
                }
            }

            Divider()
            HStack {
                Button {
                    loadProfileForEditing("new-profile", MediaProfile())
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

    private func loadProfileForEditing(
        _ name: String,
        _ newProfile: MediaProfile?,
        _ isCreatingNew: Bool = false
    ) {
        guard var profile = newProfile else { return }
        if profile.type == nil {
            profile.type = .video
        }
        editingName = name
        editingProfile = profile
        originalSnapshot = (name: name, profile: profile)
        selectedProfile = name
    }

    private func saveCurrentProfile() {
        guard let profile = editingProfile, state.profilesConfig != nil else {
            return
        }

        if let snapshot = originalSnapshot, snapshot.name != editingName {
            state.profilesConfig?.profiles.removeValue(forKey: snapshot.name)
            if state.workflowSession.profileName == snapshot.name {
                state.workflowSession.profileName = editingName
            }
        }
        state.profilesConfig?.profiles[editingName] = profile

        writeProfiles()
        originalSnapshot = (name: editingName, profile: profile)
        selectedProfile = editingName
    }

    private func deleteProfile(_ name: String) {
        state.profilesConfig?.profiles.removeValue(forKey: name)
        writeProfiles()
        if state.workflowSession.profileName == name {
            state.workflowSession = WorkflowSession()
        }
        selectedProfile = nil
        editingProfile = nil
        editingName = ""
        originalSnapshot = nil
    }

    private func duplicateProfile() {
        guard let name = selectedProfile,
            let profile = state.profile(named: name)
        else { return }

        // Generate a unique name for the duplicated profile
        let baseName = name.replacing(/\ copy \d+$/, with: "")

        var counter = 1
        var duplicateName = "\(baseName) copy \(counter)"
        while state.profile(named: duplicateName) != nil {
            duplicateName = "\(baseName) copy \(counter)"
            counter += 1
        }
        loadProfileForEditing(duplicateName, profile)
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
    @Binding var profileName: String
    @Binding var profile: MediaProfile
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
                        text: $profileName
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
                    dirField($profile.sourceDir)
                }
                GridRow {
                    Text(Strings.Profiles.readyDirLabel)
                    dirField($profile.readyDir)
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
                    ExtensionField(items: $profile.fileExtensions)
                }

                GridRow {
                    HelpLabel(
                        Strings.Profiles.companionLabel,
                        help: Strings.Profiles.companionHelp
                    )
                    ExtensionField(items: $profile.companionExtensions)
                }

                GridRow {
                    HelpLabel(
                        Strings.Profiles.tagsLabel,
                        help: Strings.Profiles.tagsHelp
                    )
                    CommaSeparatedField(
                        items: $profile.tags,
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
                    .disabled(profileName.isEmpty)
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
            get: { profile.exif?[keyPath: sub] ?? "" },
            set: { newValue in
                if profile.exif == nil { profile.exif = ExifConfig() }
                profile.exif?[keyPath: sub] = newValue.isEmpty ? nil : newValue
            }
        )
    }

    private var typeBinding: Binding<MediaType> {
        Binding(
            get: { profile.type ?? .video },
            set: { profile.type = $0 }
        )
    }

    private var gyroflowToggle: Binding<Bool> {
        Binding(
            get: { profile.gyroflowEnabled ?? false },
            set: { profile.gyroflowEnabled = $0 }
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
