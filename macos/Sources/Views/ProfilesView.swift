import SwiftUI

struct ProfileEditingSession: Equatable {
    var name: String
    var profile: MediaProfile
    var globalStabilization: StabilizationSettings?

    /// Edited since it was loaded, or never written at all — a new or duplicated
    /// profile is unchanged from its snapshot but still has to be saved. Save and
    /// Cancel only show while this holds, so their disappearing is the sign a save
    /// went through.
    static func hasUnsavedChanges(editor: Self, snapshot: Self?, isSaved: Bool) -> Bool {
        editor != snapshot || !isSaved
    }
}

struct ProfilesView: View {
    @Bindable var state: AppState
    @State private var selectedProfile: String?
    @State private var editor: ProfileEditingSession?
    @State private var snapshot: ProfileEditingSession?
    @State private var showDeleteConfirmation = false
    @State private var showDiscardConfirmation = false
    @State private var pendingAction: PendingAction?
    @State private var newCameraChoices: [SourceContents.NewCamera] = []
    @State private var showNoMediaFound = false

    private enum PendingAction {
        case loadProfile(ProfileEditingSession)
        case switchTab(SidebarTab)
        case dismiss
    }

    private var isDirty: Bool {
        guard let editor, let snapshot else { return false }
        return editor != snapshot
    }

    private var hasUnsavedChanges: Bool {
        guard let editor else { return false }
        return ProfileEditingSession.hasUnsavedChanges(
            editor: editor,
            snapshot: snapshot,
            isSaved: snapshot.flatMap { state.profile(named: $0.name) } != nil)
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
                .frame(width: Theme.Size.profileList)

            Divider()

            if editor != nil {
                ProfileEditorView(
                    session: sessionBinding,
                    gyroflowAvailable: state.gyroflowStatus.isInstalled,
                    hasUnsavedChanges: hasUnsavedChanges,
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
                    .foregroundStyle(Theme.Text.secondary)
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
        .confirmationDialog(
            Strings.Profiles.chooseCameraTitle,
            isPresented: Binding(get: { !newCameraChoices.isEmpty },
                                 set: { if !$0 { newCameraChoices = [] } })
        ) {
            ForEach(newCameraChoices, id: \.kind) { found in
                Button(found.kind.defaultProfileName) { createProfile(for: found) }
            }
            Button(Strings.Common.cancel, role: .cancel) { newCameraChoices = [] }
        }
        .alert(Strings.Profiles.noMediaFoundTitle, isPresented: $showNoMediaFound) {
            Button(Strings.Common.done, role: .cancel) {}
        } message: {
            Text(Strings.Profiles.noMediaFoundMessage)
        }
    }

    private var duplicatedProfiles: Set<String> {
        ProfileMatcher.duplicates(in: state.profilesConfig?.profiles ?? [:])
    }

    /// A profile is its camera and kind of media, so only one made by hand for
    /// files that record no camera can be copied.
    private var canDuplicateSelection: Bool {
        guard let name = selectedProfile, let profile = state.profile(named: name) else { return false }
        return CameraKind(profile: profile) == nil
    }

    // MARK: - New profiles come from media

    /// A profile starts from its source: the folder chosen becomes the source,
    /// and its files give the camera, kind of media and file types. A camera that
    /// already has a profile opens it; media that records no camera starts a
    /// profile named by hand.
    private func newProfileFromCard() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = Strings.Profiles.newProfilePanelMessage
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task {
            let probes = await CameraProbe.probe(
                path: url.path, scriptsDirectory: state.scriptsDirectory,
                profilesPath: state.profilesLocation.path)
            let contents = ProfileMatcher.contents(of: probes, source: url.path,
                                                   profiles: state.profilesConfig?.profiles ?? [:])
            if contents.newCameras.count == 1 {
                createProfile(for: contents.newCameras[0])
            } else if contents.newCameras.count > 1 {
                newCameraChoices = contents.newCameras
            } else if let existing = contents.existingProfiles.first,
                      let profile = state.profile(named: existing) {
                requestProfileLoad(ProfileEditingSession(name: existing, profile: profile))
            } else if contents.hasCameralessMedia {
                let type = probes.first { $0.camera == nil }?.type
                requestProfileLoad(ProfileEditingSession(
                    name: "new-profile",
                    profile: MediaProfile(type: type, sourceDir: url.path)))
            } else {
                showNoMediaFound = true
            }
        }
    }

    private func createProfile(for found: SourceContents.NewCamera) {
        newCameraChoices = []
        let name = state.createProfile(for: found)
        guard let profile = state.profile(named: name) else { return }
        requestProfileLoad(ProfileEditingSession(name: name, profile: profile))
    }

    private var profileList: some View {
        VStack(spacing: 0) {
            List(selection: $selectedProfile) {
                ForEach(state.sortedProfileNames, id: \.self) { name in
                    HStack(spacing: Theme.Space.md) {
                        if let profile = state.profile(named: name) {
                            Image(
                                systemName: profile.type?.systemImage
                                    ?? "questionmark"
                            )
                            .foregroundStyle(Theme.Text.secondary)
                            .frame(width: Theme.Size.listIcon)

                            let device = [
                                profile.exif?.make, profile.exif?.model,
                            ]
                            .compactMap { $0 }.joined(separator: " ")
                            VStack(alignment: .leading, spacing: Theme.Space.xxs) {
                                if !device.isEmpty {
                                    Text(device).fontWeight(.medium)
                                    Text(name)
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Text.secondary)
                                } else {
                                    Text(name).fontWeight(.medium)
                                }
                            }
                        } else {
                            Text(name).fontWeight(.medium)
                        }
                        Spacer()
                        if duplicatedProfiles.contains(name) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(Theme.Status.warning)
                                .help(Strings.Profiles.duplicateCameraHelp)
                        }
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
                    newProfileFromCard()
                } label: {
                    Image(systemName: "plus")
                        .frame(width: Theme.Size.iconButton, height: Theme.Size.iconButton)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)

                Button {
                    showDeleteConfirmation = true
                } label: {
                    Image(systemName: "minus")
                        .frame(width: Theme.Size.iconButton, height: Theme.Size.iconButton)
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
                        .frame(width: Theme.Size.iconButton, height: Theme.Size.iconButton)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.borderless)
                .disabled(!canDuplicateSelection)

                Spacer()
            }
            .padding(Theme.Space.md)
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
        session.globalStabilization = state.profilesConfig?.gyroflow?.preset?.stabilization
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

        state.writeProfiles()
        snapshot = editor
        selectedProfile = editor.name
    }

    private func deleteProfile(_ name: String) {
        state.profilesConfig?.profiles.removeValue(forKey: name)
        state.writeProfiles()
        if state.workflowSession.profileName == name {
            state.workflowSession = WorkflowSession(
                gyroflowAvailable: state.gyroflowStatus.isInstalled
            )
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
}

struct ProfileEditorView: View {
    @Binding var session: ProfileEditingSession
    /// Gyroflow is optional and not bundled with Jetlag; without an install
    /// the stabilization settings would have nothing to drive.
    let gyroflowAvailable: Bool
    let hasUnsavedChanges: Bool
    let onSave: () -> Void
    let onCancel: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.xl) {
                OptionRow(label: Strings.Profiles.nameLabel, labelWidth: Theme.Size.profileLabel) {
                    TextField(Strings.Profiles.namePlaceholder, text: $session.name)
                        .textFieldStyle(.roundedBorder)
                }

                OptionRow(
                    label: Strings.Profiles.typeLabel, help: Strings.Profiles.typeHelp,
                    labelWidth: Theme.Size.profileLabel
                ) {
                    Picker("", selection: typeBinding) {
                        Text(Strings.Profiles.videoOption).tag(MediaType.video)
                        Text(Strings.Profiles.photoOption).tag(MediaType.photo)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: Theme.Size.typePicker)
                    .disabled(CameraKind(profile: session.profile) != nil)
                }

                Divider()

                OptionRow(label: Strings.Profiles.sourceDirLabel, labelWidth: Theme.Size.profileLabel) {
                    directoryField($session.profile.sourceDir)
                }
                OptionRow(label: Strings.Profiles.readyDirLabel, labelWidth: Theme.Size.profileLabel) {
                    directoryField($session.profile.readyDir)
                }

                Divider()

                OptionRow(
                    label: Strings.Profiles.cameraLabel, help: Strings.Profiles.cameraHelp,
                    labelWidth: Theme.Size.profileLabel
                ) {
                    if let camera = FileCamera(make: session.profile.exif?.make,
                                               model: session.profile.exif?.model) {
                        Text(camera.name)
                    } else {
                        Text(Strings.Profiles.noCameraRecorded)
                            .foregroundStyle(Theme.Text.secondary)
                    }
                }

                Divider()

                OptionRow(
                    label: Strings.Profiles.fileTypesLabel, help: Strings.Profiles.fileExtensionsHelp,
                    labelWidth: Theme.Size.profileLabel
                ) {
                    ExtensionField(items: $session.profile.fileExtensions)
                }

                OptionRow(
                    label: Strings.Profiles.companionLabel, help: Strings.Profiles.companionHelp,
                    labelWidth: Theme.Size.profileLabel
                ) {
                    ExtensionField(items: $session.profile.companionExtensions)
                }

                OptionRow(
                    label: Strings.Profiles.tagsLabel, help: Strings.Profiles.tagsHelp,
                    labelWidth: Theme.Size.profileLabel
                ) {
                    CommaSeparatedField(
                        items: $session.profile.tags,
                        placeholder: Strings.Profiles.tagPlaceholder
                    )
                }

                if session.profile.type != .photo && gyroflowAvailable {
                    Divider()

                    ToggleRow(
                        title: Strings.Profiles.gyroflowToggle,
                        isOn: gyroflowToggle,
                        help: Strings.Profiles.gyroflowHelp
                    )
                    .padding(.leading, Theme.Size.profileLabel + Theme.Space.sm)

                    if session.profile.gyroflowEnabled == true {
                        gyroflowSettingsRows
                    }
                }
            }
            .padding(Theme.Space.xxxl)
        }
        .safeAreaInset(edge: .bottom) {
            if hasUnsavedChanges {
                HStack {
                    Spacer()
                    Button(Strings.Common.cancel) { onCancel() }
                        .keyboardShortcut(.escape)
                    Button(Strings.Profiles.saveButton) { onSave() }
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)
                        .disabled(session.name.isEmpty)
                }
                .padding(Theme.Space.xxxl)
                .background(Theme.Surface.bar)
            }
        }
    }

    private func directoryField(_ binding: Binding<String?>) -> some View {
        PathField(placeholder: "", path: optionalBinding(binding), error: nil)
    }

    private func optionalBinding(_ binding: Binding<String?>) -> Binding<String>
    {
        Binding(
            get: { binding.wrappedValue ?? "" },
            set: { binding.wrappedValue = $0.isEmpty ? nil : $0 }
        )
    }

    private var typeBinding: Binding<MediaType> {
        Binding(
            get: { session.profile.type ?? .video },
            set: { newValue in
                session.profile.type = newValue
                if newValue == .photo {
                    session.profile.gyroflowEnabled = nil
                    session.profile.gyroflowSettings = nil
                }
            }
        )
    }

    private var gyroflowToggle: Binding<Bool> {
        Binding(
            get: { session.profile.gyroflowEnabled ?? false },
            set: { newValue in
                session.profile.gyroflowEnabled = newValue
                if newValue {
                    if session.profile.gyroflowSettings == nil {
                        session.profile.gyroflowSettings = session.globalStabilization ?? StabilizationSettings()
                    }
                } else {
                    session.profile.gyroflowSettings = nil
                }
            }
        )
    }

    private var gyroflowSettingsRows: some View {
        Group {
            OptionRow(
                label: Strings.Profiles.maxZoomLabel, help: Strings.Profiles.maxZoomHelp,
                labelWidth: Theme.Size.profileLabel
            ) {
                TextField("", value: stabilizationBinding(\.maxZoom), format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: Theme.Size.gyroflowNumberField)
            }

            OptionRow(
                label: Strings.Profiles.adaptiveZoomWindowLabel, help: Strings.Profiles.adaptiveZoomWindowHelp,
                labelWidth: Theme.Size.profileLabel
            ) {
                TextField("", value: stabilizationBinding(\.adaptiveZoomWindow), format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: Theme.Size.gyroflowNumberField)
            }

            OptionRow(
                label: Strings.Profiles.adaptiveZoomMethodLabel, help: Strings.Profiles.adaptiveZoomMethodHelp,
                labelWidth: Theme.Size.profileLabel
            ) {
                Picker("", selection: zoomMethodBinding) {
                    ForEach(AdaptiveZoomMethod.allCases) { method in
                        Text(method.label).tag(method)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: Theme.Size.zoomMethodPicker)
            }
        }
    }

    private func stabilizationBinding(_ keyPath: WritableKeyPath<StabilizationSettings, Double?>) -> Binding<Double?> {
        Binding(
            get: { session.profile.gyroflowSettings?[keyPath: keyPath] },
            set: { newValue in
                if session.profile.gyroflowSettings == nil {
                    session.profile.gyroflowSettings = StabilizationSettings()
                }
                session.profile.gyroflowSettings?[keyPath: keyPath] = newValue
            }
        )
    }

    private var zoomMethodBinding: Binding<AdaptiveZoomMethod> {
        Binding(
            get: {
                AdaptiveZoomMethod(rawValue: session.profile.gyroflowSettings?.adaptiveZoomMethod ?? 1) ?? .dynamic
            },
            set: { newValue in
                if session.profile.gyroflowSettings == nil {
                    session.profile.gyroflowSettings = StabilizationSettings()
                }
                session.profile.gyroflowSettings?.adaptiveZoomMethod = newValue.rawValue
            }
        )
    }
}
