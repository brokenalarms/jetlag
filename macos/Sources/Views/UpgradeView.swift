import SwiftUI

struct UpgradeView: View {
    let fileCount: Int
    @Bindable var store: LicenseStore
    var onDismiss: () -> Void
    var onUnlocked: () -> Void

    @State private var licenseKey = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            HStack(spacing: 12) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(Strings.Upgrade.title)
                        .font(.title2.bold())
                    Text(Strings.Upgrade.subtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            Divider()

            // Limit message
            VStack(alignment: .leading, spacing: 6) {
                Text(Strings.Upgrade.jobFileCount(fileCount))
                    .font(.body)
                Text(Strings.Upgrade.freeLimit(fileLimit: store.fileLimit))
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            // Value prop
            Text(Strings.Upgrade.valueProp)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            // License key entry
            VStack(alignment: .leading, spacing: 8) {
                Text(Strings.Upgrade.alreadyPurchased)
                    .font(.subheadline.weight(.medium))

                HStack(spacing: 8) {
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
                        .font(.caption)
                        .foregroundStyle(.red)
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
        .padding(24)
        .frame(width: 420)
    }

    private func activate() async {
        await store.activate(licenseKey: licenseKey.trimmingCharacters(in: .whitespaces))
        if store.isUnlocked {
            onUnlocked()
        }
    }
}
