import SwiftUI

struct ToggleRow: View {
    let title: String
    var caption: String?
    @Binding var isOn: Bool
    var isEnabled = true
    var help: String?

    var body: some View {
        HStack(spacing: Theme.Space.sm) {
            Toggle(isOn: $isOn) {
                VStack(alignment: .leading, spacing: Theme.Space.xxs) {
                    Text(title)
                    if let caption {
                        Text(caption)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Text.secondary)
                    }
                }
            }
            .disabled(!isEnabled)
            if let help {
                HelpButton(help)
            }
        }
    }
}
