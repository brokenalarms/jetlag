import SwiftUI

struct ToggleRow: View {
    let title: String
    var caption: String?
    @Binding var isOn: Bool
    var isEnabled = true
    var help: String?

    @Environment(\.isEnabled) private var environmentEnabled

    /// A disabled switch-style toggle keeps its label at full strength, and in dark mode
    /// an off switch looks the same enabled or not, so the label carries the dimming.
    private var isDimmed: Bool { !(isEnabled && environmentEnabled) }

    var body: some View {
        HStack(spacing: Theme.Space.sm) {
            Toggle(isOn: $isOn) {
                VStack(alignment: .leading, spacing: Theme.Space.xxs) {
                    Text(title)
                        .foregroundStyle(isDimmed ? Theme.Text.tertiary : Theme.Text.primary)
                    if let caption {
                        Text(caption)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(isDimmed ? Theme.Text.tertiary : Theme.Text.secondary)
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
