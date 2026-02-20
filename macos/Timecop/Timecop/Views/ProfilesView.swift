import SwiftUI

struct ProfilesView: View {
    @Bindable var state: AppState
    @State private var selectedProfile: String?
    @State private var editingProfile: (name: String, profile: MediaProfile)?
    @State private var isCreatingNew = false
    @State private var showDeleteConfirmation = false

    var body: some View {
        HStack(spacing: 0) {
            profileList
                .frame(width: 200)

            Divider()

            if let (name, profile) = editingProfile {
                ProfileEditorView(
                    profileName: name,
                    profile: profile,
                    isNew: isCreatingNew,
                    onSave: { savedName, savedProfile in saveProfile(name: savedName, profile: savedProfile) },
                    onCancel: { self.editingProfile = nil; isCreatingNew = false }
                )
                .frame(maxWidth: .infinity)
            } else {
                Text("Select a profile to edit")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle("Media Profiles")
    }

    private var profileList: some View {
        VStack(spacing: 0) {
            List(selection: $selectedProfile) {
                ForEach(state.sortedProfileNames, id: \.self) { name in
                    HStack(spacing: 6) {
                        if let profile = state.profile(named: name) {
                            Image(systemName: profile.type?.systemImage ?? "questionmark")
                                .foregroundStyle(.secondary)
                                .frame(width: 14)

                            let device = [profile.exif?.make, profile.exif?.model]
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
                guard !isCreatingNew else { return }
                if let name = newValue, let profile = state.profile(named: name) {
                    editingProfile = (name: name, profile: profile)
                }
            }

            Divider()
            HStack {
                Button {
                    isCreatingNew = true
                    selectedProfile = nil
                    editingProfile = (name: "new-profile", profile: MediaProfile())
                } label: {
                    Image(systemName: "plus")
                }
                .buttonStyle(.borderless)

                Button {
                    showDeleteConfirmation = true
                } label: {
                    Image(systemName: "minus")
                }
                .buttonStyle(.borderless)
                .disabled(selectedProfile == nil)
                .confirmationDialog(
                    "Delete profile \"\(selectedProfile ?? "")\"?",
                    isPresented: $showDeleteConfirmation,
                    titleVisibility: .visible
                ) {
                    Button("Delete", role: .destructive) {
                        if let name = selectedProfile {
                            deleteProfile(name)
                        }
                    }
                } message: {
                    Text("This will remove the profile from media-profiles.yaml. This cannot be undone.")
                }

                Spacer()
            }
            .padding(6)
        }
    }

    private func saveProfile(name: String, profile: MediaProfile) {
        guard state.profilesConfig != nil else { return }

        if isCreatingNew {
            state.profilesConfig?.profiles[name] = profile
        } else if let oldName = selectedProfile {
            if oldName != name {
                state.profilesConfig?.profiles.removeValue(forKey: oldName)
            }
            state.profilesConfig?.profiles[name] = profile
        }

        writeProfiles()
        selectedProfile = name
        editingProfile = (name: name, profile: profile)
        isCreatingNew = false
    }

    private func deleteProfile(_ name: String) {
        state.profilesConfig?.profiles.removeValue(forKey: name)
        writeProfiles()
        selectedProfile = nil
        editingProfile = nil
    }

    private func writeProfiles() {
        guard let config = state.profilesConfig else { return }
        do {
            try ProfileService.write(config, to: state.resolvedProfilesPath)
        } catch {
            state.profileLoadError = ProfileLoadError(
                message: "Failed to write profiles",
                filePath: state.resolvedProfilesPath,
                detail: error.localizedDescription
            )
        }
    }
}

struct ProfileEditorView: View {
    @State var profileName: String
    @State var profile: MediaProfile
    let isNew: Bool
    let onSave: (String, MediaProfile) -> Void
    let onCancel: () -> Void

    var body: some View {
        ScrollView {
            Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    Text("Name").gridColumnAlignment(.trailing)
                    TextField("profile-name", text: $profileName)
                        .textFieldStyle(.roundedBorder)
                }

                GridRow {
                    HelpLabel("Type", help: Strings.Profiles.type)
                    Picker("", selection: typeBinding) {
                        Text("Video").tag(MediaType.video)
                        Text("Photo").tag(MediaType.photo)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 160)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text("Source dir")
                    dirField($profile.sourceDir)
                }
                GridRow {
                    Text("Import dir")
                    dirField($profile.importDir)
                }
                GridRow {
                    Text("Ready dir")
                    dirField($profile.readyDir)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text("EXIF Make")
                    TextField("e.g. Sony", text: exifBinding(\.make))
                        .textFieldStyle(.roundedBorder)
                }
                GridRow {
                    Text("EXIF Model")
                    TextField("e.g. ILCE-7M4", text: exifBinding(\.model))
                        .textFieldStyle(.roundedBorder)
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    HelpLabel("File types", help: Strings.Profiles.fileExtensions)
                    ExtensionField(items: $profile.fileExtensions)
                }

                GridRow {
                    HelpLabel("Companion", help: Strings.Profiles.companion)
                    ExtensionField(items: $profile.companionExtensions)
                }

                GridRow {
                    HelpLabel("Tags", help: Strings.Profiles.tags)
                    CommaSeparatedField(items: $profile.tags, placeholder: "tag1, tag2")
                }

                Divider().gridCellUnsizedAxes(.horizontal)

                GridRow {
                    Text("")
                    HStack(spacing: 4) {
                        Toggle("Gyroflow", isOn: gyroflowToggle)
                        HelpButton(Strings.Profiles.gyroflow)
                    }
                }
            }
            .padding()
        }
        .safeAreaInset(edge: .bottom) {
            HStack {
                Spacer()
                Button("Cancel") { onCancel() }
                    .keyboardShortcut(.escape)
                Button(isNew ? "Create" : "Update") { onSave(profileName, profile) }
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
            Button("Browse...") {
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

    private func optionalBinding(_ binding: Binding<String?>) -> Binding<String> {
        Binding(
            get: { binding.wrappedValue ?? "" },
            set: { binding.wrappedValue = $0.isEmpty ? nil : $0 }
        )
    }

    private func exifBinding(_ sub: WritableKeyPath<ExifConfig, String?>) -> Binding<String> {
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

