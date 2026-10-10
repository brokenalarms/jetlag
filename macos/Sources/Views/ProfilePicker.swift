import SwiftUI

struct ProfilePicker: View {
    @Binding var selection: String
    let state: AppState

    /// A pull-down rather than a pop-up: a pop-up menu opens with the selected item over
    /// the button, so with a later profile chosen it extends upward and, near the top
    /// of the screen, hides the earlier profiles behind a scroll arrow. A pull-down
    /// always opens below; the inline picker inside still checks the current profile.
    var body: some View {
        Menu {
            Picker("", selection: $selection) {
                Text(Strings.Workflow.selectProfile).tag("")
                ForEach(state.sortedProfileNames, id: \.self) { name in
                    profileLabel(name: name).tag(name)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            if selection.isEmpty {
                Text(Strings.Workflow.selectProfile)
            } else {
                profileLabel(name: selection)
            }
        }
        .fixedSize()
    }

    private func profileLabel(name: String) -> some View {
        let profile = state.profile(named: name)
        let make = profile?.exif?.make
        let model = profile?.exif?.model
        let deviceName = [make, model].compactMap { $0 }.joined(separator: " ")
        let typeImage = profile?.type?.systemImage ?? "questionmark"

        return HStack(spacing: 6) {
            Image(systemName: typeImage)
                .frame(width: 14)
                .foregroundStyle(.secondary)
            if !deviceName.isEmpty {
                Text(deviceName)
                Text(name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text(name)
            }
        }
    }
}
