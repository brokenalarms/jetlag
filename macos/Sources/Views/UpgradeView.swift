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
                    Text("Jetlag Pro")
                        .font(.title2.bold())
                    Text("Unlimited file processing")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            Divider()

            // Limit message
            VStack(alignment: .leading, spacing: 6) {
                Text("This job has \(fileCount) files.")
                    .font(.body)
                Text("The free version processes up to \(store.fileLimit) files per run.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            // Value prop
            Text("Unlock Jetlag Pro for unlimited processing — one-time purchase, no subscription.")
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            // License key entry
            VStack(alignment: .leading, spacing: 8) {
                Text("Already purchased?")
                    .font(.subheadline.weight(.medium))

                HStack(spacing: 8) {
                    TextField("License key", text: $licenseKey)
                        .textFieldStyle(.roundedBorder)
                        .disabled(store.isActivating)

                    Button(store.isActivating ? "Activating…" : "Activate") {
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
                Button("Buy Jetlag Pro") {
                    NSWorkspace.shared.open(URL(string: "https://jetlag.app")!)
                }
                .buttonStyle(.borderedProminent)

                Spacer()

                Button("Cancel", role: .cancel) { onDismiss() }
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
