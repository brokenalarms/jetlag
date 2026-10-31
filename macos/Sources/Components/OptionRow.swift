import SwiftUI

/// Rows of an `OptionGroup` share one label column and one control column.
struct OptionGroup<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        Grid(alignment: .leadingFirstTextBaseline,
             horizontalSpacing: Theme.Space.xxl,
             verticalSpacing: Theme.Space.xl) {
            content
        }
    }
}

/// A label and a control on one row of an `OptionGroup`. With `help` the label is a `HelpLabel`.
/// The control must be a single view so it occupies the group's one control column.
struct OptionRow<Control: View>: View {
    let label: String
    var help: String?
    @ViewBuilder let control: Control

    var body: some View {
        GridRow {
            labelView
                .gridColumnAlignment(.trailing)
            control
        }
    }

    @ViewBuilder
    private var labelView: some View {
        if let help {
            HelpLabel(label, help: help)
        } else {
            Text(label)
        }
    }
}
