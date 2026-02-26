import SwiftUI

struct ProfilePicker: View {
    @Binding var selection: String
    let state: AppState

    var body: some View {
        Picker("", selection: $selection) {
            Text(Strings.Workflow.selectProfile).tag("")
            ForEach(state.sortedProfileNames, id: \.self) { name in
                profileLabel(name: name).tag(name)
            }
        }
        .labelsHidden()
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
