import SwiftUI

struct ActionMode<Value: Hashable>: Identifiable {
    let title: String
    let value: Value
    var id: String { title }
}

/// A mode picker, the primary action, and — while running — Cancel.
struct ActionBar<Mode: Hashable>: View {
    let modes: [ActionMode<Mode>]
    @Binding var mode: Mode
    let primaryTitle: String
    let cancelTitle: String
    let isRunning: Bool
    let canRun: Bool
    let onRun: () -> Void
    let onCancel: () -> Void

    var body: some View {
        HStack(spacing: Theme.Space.xxl) {
            Picker("", selection: $mode) {
                ForEach(modes) { Text($0.title).tag($0.value) }
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .fixedSize()
            .disabled(isRunning)

            Button(primaryTitle, action: onRun)
                .disabled(isRunning || !canRun)
                .keyboardShortcut(.return, modifiers: .command)
                .buttonStyle(.borderedProminent)

            if isRunning {
                Button(cancelTitle, role: .destructive, action: onCancel)
            }

            Spacer()
        }
        .padding(.horizontal, Theme.Space.xxxl)
        .padding(.vertical, Theme.Space.xl)
        .background(Theme.Surface.bar)
    }
}
