import SwiftUI

struct SettingsView: View {
    @Bindable var state: AppState

    var body: some View {
        Form {
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
