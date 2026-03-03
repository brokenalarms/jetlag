import SwiftUI

struct SettingsView: View {
    @Bindable var state: AppState
    @State private var licenseKey = ""
    private var licenseStore: LicenseStore { LicenseStore.shared }

    var body: some View {
        Form {
            Section(Strings.Settings.licenseSection) {
                if licenseStore.isUnlocked {
                    Label(Strings.Settings.proActivated, systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                } else {
                    LabeledContent(Strings.Settings.planLabel) {
                        Text(Strings.Settings.freePlan(fileLimit: licenseStore.fileLimit))
                            .foregroundStyle(.secondary)
                    }

                    HStack(spacing: 8) {
                        TextField(Strings.Settings.licenseKeyPlaceholder, text: $licenseKey)
                            .textFieldStyle(.roundedBorder)
                            .disabled(licenseStore.isActivating)
                        Button(licenseStore.isActivating ? Strings.Settings.activatingButton : Strings.Settings.activateButton) {
                            Task { await licenseStore.activate(licenseKey: licenseKey.trimmingCharacters(in: .whitespaces)) }
                        }
                        .disabled(licenseKey.trimmingCharacters(in: .whitespaces).isEmpty || licenseStore.isActivating)
                    }

                    if let error = licenseStore.activationError {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.red)
                    }

                    Button(Strings.Settings.buyProButton) {
                        NSWorkspace.shared.open(URL(string: "https://jetlag.app")!)
                    }
                }
            }

            Section(Strings.Settings.scriptsSection) {
                LabeledContent(Strings.Settings.scriptsDirLabel) {
                    Text(state.scriptsDirectory)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                HStack {
                    TextField(
                        Strings.Settings.profilesFilePlaceholder,
                        text: $state.profilesFilePath
                    )
                    .textFieldStyle(.roundedBorder)
                    Button(Strings.Common.browse) { pickFile() }
                }
            }

            Section {
                HStack {
                    if let error = state.profileLoadError {
                        Label(error.displayMessage, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                            .font(.caption)
                    } else if let config = state.profilesConfig {
                        Label(
                            Strings.Settings.profilesLoaded(count: config.profiles.count),
                            systemImage: "checkmark.circle"
                        )
                        .foregroundStyle(.green)
                        .font(.caption)
                    }
                    Spacer()
                    Button(Strings.Settings.reloadProfilesButton) { loadProfiles() }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 500)
        .padding()
    }

    private func loadProfiles() {
        do {
            state.profilesConfig = try ProfileService.load(from: state.resolvedProfilesPath).normalized()
            state.profileLoadError = nil
        } catch {
            state.profilesConfig = nil
            state.profileLoadError = error
        }
    }

    private func pickFile() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.yaml]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            state.profilesFilePath = url.path
        }
    }
}
