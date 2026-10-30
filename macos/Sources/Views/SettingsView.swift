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
                        .foregroundStyle(Theme.Status.success)
                } else {
                    LabeledContent(Strings.Settings.planLabel) {
                        Text(Strings.Settings.freePlan(fileLimit: licenseStore.fileLimit))
                            .foregroundStyle(Theme.Text.secondary)
                    }

                    HStack(spacing: Theme.Space.lg) {
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
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Status.failure)
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
                        .foregroundStyle(Theme.Status.success)
                    LabeledContent(Strings.Settings.gyroflowSourceLabel) {
                        Text(state.gyroflowStatus.displayName)
                            .foregroundStyle(Theme.Text.secondary)
                            .textSelection(.enabled)
                    }
                } else {
                    Label(Strings.Settings.gyroflowMissing, systemImage: "info.circle")
                        .foregroundStyle(Theme.Text.secondary)
                        .font(Theme.Typography.caption)

                    HStack(spacing: Theme.Space.lg) {
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
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Text.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        } else {
                            Text(Strings.Settings.gyroflowDownloadNote)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Text.secondary)
                        }
                    }
                }
            }

            Section(Strings.Settings.scriptsSection) {
                LabeledContent(Strings.Settings.scriptsDirLabel) {
                    Text(state.scriptsDirectory)
                        .foregroundStyle(Theme.Text.secondary)
                        .textSelection(.enabled)
                }

                LabeledContent(Strings.Settings.profilesFileLabel) {
                    HStack(spacing: Theme.Space.lg) {
                        Text(state.profilesLocation.path)
                            .foregroundStyle(Theme.Text.secondary)
                            .textSelection(.enabled)
                            .truncationMode(.middle)
                            .lineLimit(1)
                        Button(Strings.Common.revealInFinder) { revealProfilesFile() }
                            .buttonStyle(.link)
                    }
                }
            }

            Section {
                HStack {
                    if let error = state.profileLoadError {
                        Label(error.displayMessage, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(Theme.Status.failure)
                            .font(Theme.Typography.caption)
                    } else if let config = state.profilesConfig {
                        Label(
                            Strings.Settings.profilesLoaded(count: config.profiles.count),
                            systemImage: "checkmark.circle"
                        )
                        .foregroundStyle(Theme.Status.success)
                        .font(Theme.Typography.caption)
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
            [URL(fileURLWithPath: state.profilesLocation.path)])
    }
}
