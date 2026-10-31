import SwiftUI

struct UpgradeView: View {
    let fileCount: Int
    @Bindable var store: LicenseStore
    var onDismiss: () -> Void
    var onUnlocked: () -> Void

    @State private var licenseKey = ""

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.section) {
            // Header
            HStack(spacing: Theme.Space.xxl) {
                Image(systemName: "lock.fill")
                    .font(Theme.Typography.hero)
                    .foregroundStyle(Theme.Text.secondary)
                VStack(alignment: .leading, spacing: Theme.Space.xxs) {
                    Text(Strings.Upgrade.title)
                        .font(Theme.Typography.title)
                    Text(Strings.Upgrade.subtitle)
                        .font(Theme.Typography.subheadline)
                        .foregroundStyle(Theme.Text.secondary)
                }
            }

            Divider()

            // Limit message
            VStack(alignment: .leading, spacing: Theme.Space.md) {
                Text(Strings.Upgrade.jobFileCount(fileCount))
                    .font(Theme.Typography.body)
                Text(Strings.Upgrade.freeLimit(fileLimit: store.fileLimit))
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Text.secondary)
            }

            // Value prop
            Text(Strings.Upgrade.valueProp)
                .font(Theme.Typography.body)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            // License key entry
            VStack(alignment: .leading, spacing: Theme.Space.lg) {
                Text(Strings.Upgrade.alreadyPurchased)
                    .font(Theme.Typography.subheadlineMedium)

                HStack(spacing: Theme.Space.lg) {
                    TextField(Strings.Settings.licenseKeyPlaceholder, text: $licenseKey)
                        .textFieldStyle(.roundedBorder)
                        .disabled(store.isActivating)

                    Button(store.isActivating ? Strings.Settings.activatingButton : Strings.Settings.activateButton) {
                        Task { await activate() }
                    }
                    .disabled(licenseKey.trimmingCharacters(in: .whitespaces).isEmpty || store.isActivating)
                }

                if let error = store.activationError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Status.failure)
                }
            }

            // CTA + cancel
            HStack {
                Button(Strings.Settings.buyProButton) {
                    NSWorkspace.shared.open(URL(string: "https://jetlag.app")!)
                }
                .buttonStyle(.borderedProminent)

                Spacer()

                Button(Strings.Common.cancel, role: .cancel) { onDismiss() }
            }
        }
        .padding(Theme.Space.page)
        .frame(width: Theme.Size.upgradeWidth)
    }

    private func activate() async {
        await store.activate(licenseKey: licenseKey.trimmingCharacters(in: .whitespaces))
        if store.isUnlocked {
            onUnlocked()
        }
    }
}
