import SwiftUI

enum StatusBadgeState: Equatable {
    case done
    case wouldDo
    case unchanged
    case failed
    case pending
    case plain
    case custom(icon: String, tint: Color)
}

/// Icon and label for a semantic state. A pending state shows a spinner, with the
/// label as the stage the item last completed; a plain state is the label alone.
struct StatusBadge: View {
    let state: StatusBadgeState
    let label: String

    var body: some View {
        switch state {
        case .done:
            badge("checkmark.circle.fill", AnyShapeStyle(Theme.Accent.highlight))
        case .wouldDo:
            badge("arrow.triangle.2.circlepath.circle.fill",
                  AnyShapeStyle(Theme.Accent.highlight.opacity(Theme.Tint.dimmedHighlight)))
        case .unchanged:
            badge("minus.circle.fill", AnyShapeStyle(Theme.Text.secondary))
        case .failed:
            badge("xmark.circle.fill", AnyShapeStyle(Theme.Status.failure))
        case .custom(let icon, let tint):
            badge(icon, AnyShapeStyle(tint))
        case .pending:
            HStack(spacing: Theme.Space.xxs) {
                ProgressView()
                    .controlSize(.small)
                if !label.isEmpty {
                    Text(label)
                        .font(Theme.Typography.detailIcon)
                        .foregroundStyle(Theme.Text.secondary)
                }
            }
        case .plain:
            Text(label)
                .font(Theme.Typography.file)
                .foregroundStyle(Theme.Text.secondary)
        }
    }

    private func badge(_ icon: String, _ style: AnyShapeStyle) -> some View {
        Label(label, systemImage: icon)
            .font(Theme.Typography.file)
            .foregroundStyle(style)
    }
}
