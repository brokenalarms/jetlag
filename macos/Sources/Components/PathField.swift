import AppKit
import SwiftUI

/// A directory path: an editable field, a Browse button that opens a folder panel, and
/// the validation error beneath. `onCommit` runs when the path is settled — submitted,
/// the field blurred, or a folder chosen.
struct PathField: View {
    let placeholder: String
    @Binding var path: String
    let error: String?
    var help: String?
    var onCommit: (() -> Void)?
    @FocusState private var isEditing: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sm) {
            HStack(spacing: Theme.Space.md) {
                TextField(placeholder, text: $path)
                    .textFieldStyle(.roundedBorder)
                    .truncationMode(.head)
                    .help(path)
                    .focused($isEditing)
                    .onSubmit { onCommit?() }
                    .onChange(of: isEditing) { _, editing in
                        if !editing { onCommit?() }
                    }
                Button(Strings.Common.browse) { browse() }
                    .controlSize(.small)
                if let help {
                    HelpButton(help)
                }
            }
            .fieldError(error)
        }
    }

    private func browse() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            path = url.path
            onCommit?()
        }
    }
}
