import SwiftUI

struct Card<Content: View>: View {
    let title: String
    let icon: String
    let tint: Color
    let help: String
    let isRequired: Bool
    let isActive: Bool
    let onToggle: () -> Void
    @ViewBuilder let content: Content

    var body: some View {
        VStack(spacing: 0) {
            header
            if isActive {
                Divider()
                content
                    .padding(Theme.Space.xl)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.card)
                .strokeBorder(
                    isActive ? tint.opacity(isRequired ? Theme.Tint.borderAlwaysOn : Theme.Tint.border)
                             : Theme.Text.secondaryColor.opacity(Theme.Tint.borderInactive),
                    lineWidth: Theme.Stroke.hairline
                )
        )
    }

    @ViewBuilder
    private var header: some View {
        if isRequired {
            headerContent
        } else {
            Button(action: onToggle) { headerContent }
                .buttonStyle(.plain)
        }
    }

    private var headerContent: some View {
        HStack(spacing: Theme.Space.lg) {
            Image(systemName: icon)
                .font(Theme.Typography.step)
                .foregroundStyle(isActive ? tint : Theme.Text.secondaryColor)
                .frame(width: Theme.Size.headerIcon)

            Text(title)
                .font(Theme.Typography.stepMedium)

            HelpButton(help)

            Spacer()

            if isRequired {
                Text(Strings.Workflow.requiredLabel)
                    .font(Theme.Typography.chip)
                    .foregroundStyle(Theme.Text.tertiary)
            } else {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isActive ? tint : Theme.Text.secondaryColor)
            }
        }
        .padding(.horizontal, Theme.Space.xl)
        .padding(.vertical, Theme.Space.lg)
        .background(isActive ? tint.opacity(isRequired ? Theme.Tint.headerAlwaysOn : Theme.Tint.header) : Theme.Surface.clear)
        .foregroundStyle(isActive ? Theme.Text.primary : Theme.Text.secondary)
        .contentShape(Rectangle())
    }
}
