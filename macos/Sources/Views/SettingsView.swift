import SwiftUI

struct SettingsView: View {
    @Bindable var state: AppState
    @State private var licenseKey = ""
    private var licenseStore: LicenseStore { LicenseStore.shared }

    var body: some View {
        Form {
            Section("License") {
                if licenseStore.isUnlocked {
                    Label("Jetlag Pro — Activated", systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                } else {
                    LabeledContent("Plan") {
                        Text("Free — up to \(licenseStore.fileLimit) files per run")
                            .foregroundStyle(.secondary)
                    }

                    HStack(spacing: 8) {
                        TextField("License key", text: $licenseKey)
                            .textFieldStyle(.roundedBorder)
                            .disabled(licenseStore.isActivating)
                        Button(licenseStore.isActivating ? "Activating…" : "Activate") {
                            Task { await licenseStore.activate(licenseKey: licenseKey.trimmingCharacters(in: .whitespaces)) }
                        }
                        .disabled(licenseKey.trimmingCharacters(in: .whitespaces).isEmpty || licenseStore.isActivating)
                    }

                    if let error = licenseStore.activationError {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.red)
                    }

                    Button("Buy Jetlag Pro") {
                        NSWorkspace.shared.open(URL(string: "https://jetlag.app")!)
                    }
                }
            }

            Section("Scripts") {
                LabeledContent("Scripts directory") {
                    Text(state.scriptsDirectory)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                HStack {
                    TextField(
                        "Profiles file (default: scripts_dir/media-profiles.yaml)",
                        text: $state.profilesFilePath
                    )
                    .textFieldStyle(.roundedBorder)
                    Button("Browse...") { pickFile() }
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
                            "\(config.profiles.count) profiles loaded",
                            systemImage: "checkmark.circle"
                        )
                        .foregroundStyle(.green)
                        .font(.caption)
                    }
                    Spacer()
                    Button("Reload Profiles") { loadProfiles() }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 500)
        .padding()
    }

    private func loadProfiles() {
        do {
            state.profilesConfig = try ProfileService.load(from: state.resolvedProfilesPath)
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
