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

                #if DEBUG
                Toggle(Strings.Settings.debugUnlockToggle, isOn: Bindable(licenseStore).isUnlocked)
                #endif
            }

            Section(Strings.Settings.gyroflowSection) {
                if state.gyroflowStatus.isInstalled {
                    Label(Strings.Settings.gyroflowInstalled, systemImage: "checkmark.circle")
                        .foregroundStyle(.green)
                    LabeledContent(Strings.Settings.gyroflowSourceLabel) {
                        Text(state.gyroflowStatus.displayName)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                } else {
                    Label(Strings.Settings.gyroflowMissing, systemImage: "info.circle")
                        .foregroundStyle(.secondary)
                        .font(.caption)

                    HStack(spacing: 8) {
                        Button(state.isInstallingGyroflow
                               ? Strings.Settings.gyroflowInstallingButton
                               : Strings.Settings.gyroflowInstallButton) {
                            Task { await state.installGyroflow() }
                        }
                        .disabled(state.isInstallingGyroflow)

                        if state.isInstallingGyroflow {
                            ProgressView()
                                .controlSize(.small)
                            Text(state.gyroflowInstallProgress ?? "")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        } else {
                            Text(Strings.Settings.gyroflowDownloadNote)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section(Strings.Settings.scriptsSection) {
                LabeledContent(Strings.Settings.scriptsDirLabel) {
                    Text(state.scriptsDirectory)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                LabeledContent(Strings.Settings.profilesFileLabel) {
                    HStack(spacing: 8) {
                        Text(state.resolvedProfilesPath)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .truncationMode(.middle)
                            .lineLimit(1)
                        Button(Strings.Common.revealInFinder) { revealProfilesFile() }
                            .buttonStyle(.link)
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        TextField(
                            Strings.Settings.profilesFilePlaceholder(
                                defaultPath: (state.profilesLocation.path as NSString)
                                    .abbreviatingWithTildeInPath),
                            text: $state.profilesFilePath
                        )
                        .textFieldStyle(.roundedBorder)
                        Button(Strings.Common.browse) { pickFile() }
                    }
                    Text(Strings.Settings.profilesFileHelp)
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
        .task { await state.refreshGyroflowStatus() }
    }

    private func loadProfiles() {
        state.loadProfiles()
    }

    private func revealProfilesFile() {
        NSWorkspace.shared.activateFileViewerSelecting(
            [URL(fileURLWithPath: state.resolvedProfilesPath)])
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
