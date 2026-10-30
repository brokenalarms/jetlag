import SwiftUI

/// A label and a control on one line. With `help` the label is a `HelpLabel`; without it,
/// a caption. `labelWidth` right-aligns the label in a fixed column so stacked rows line up.
struct OptionRow<Control: View>: View {
    let label: String
    var help: String?
    var labelWidth: CGFloat?
    @ViewBuilder let control: Control

    var body: some View {
        HStack(spacing: Theme.Space.sm) {
            labelView
                .frame(width: labelWidth, alignment: .trailing)
            control
        }
    }

    @ViewBuilder
    private var labelView: some View {
        if let help {
            HelpLabel(label, help: help)
        } else {
            Text(label)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Text.secondary)
        }
    }
}
