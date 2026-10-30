import SwiftUI

struct Chip: Identifiable {
    let id: String
    let icon: String
    let label: String
    let tint: Color
}

/// Labelled chips when the whole row fits on one line; otherwise icons only, named on
/// hover. A chip's label never wraps: squeezed, every label broke mid-word.
struct ChipBar: View {
    let chips: [Chip]

    var body: some View {
        ViewThatFits(in: .horizontal) {
            row(showsLabels: true)
            row(showsLabels: false)
        }
    }

    private func row(showsLabels: Bool) -> some View {
        HStack(spacing: 0) {
            ForEach(Array(chips.enumerated()), id: \.element.id) { index, chip in
                HStack(spacing: Theme.Space.sm) {
                    Image(systemName: chip.icon)
                        .font(Theme.Typography.detail)
                    if showsLabels {
                        Text(chip.label)
                            .font(Theme.Typography.chip)
                            .lineLimit(1)
                            .fixedSize()
                    }
                }
                .help(chip.label)
                .foregroundStyle(Theme.Text.primary)
                .padding(.horizontal, Theme.Space.lg)
                .padding(.vertical, Theme.Space.sm)
                .background(
                    RoundedRectangle(cornerRadius: Theme.Radius.chip)
                        .fill(chip.tint.opacity(Theme.Tint.chip))
                )
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.chip))

                if index < chips.count - 1 {
                    Image(systemName: "chevron.forward")
                        .font(Theme.Typography.chipSeparator)
                        .foregroundStyle(Theme.Text.secondaryColor.opacity(Theme.Tint.chipSeparator))
                        .padding(.horizontal, Theme.Space.hairline)
                }
            }
            Spacer()
        }
        .padding(.horizontal, Theme.Space.md)
        .padding(.vertical, Theme.Space.sm)
    }
}
