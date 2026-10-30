import SwiftUI

struct ResultsHeader {
    let icon: String
    let title: String
    let count: String?
}

enum ResultsPhase {
    case content(ResultsHeader)
    /// Scanning a card takes a while before the first file lands in the table.
    /// Without the pipeline's own progress lines this reads as a hang.
    case startingUp(label: String, status: String?)
    /// Nothing to show, and the reason is worth stating with the thing it is about.
    case message(title: String, detail: String)
    /// Nothing has run yet. Gives way to the log, which takes the space when open.
    case idle(label: String)
}

/// The results side of the window: header and content (or a placeholder for the
/// phase the run is in), the command-output log, and the bar that toggles it.
struct ResultsPanel<Content: View>: View {
    /// The narrowest the content is still readable at. Declaring it here is what makes
    /// opening the panel widen the window: the window's minimum grows by this amount, so
    /// AppKit extends the right edge instead of squeezing the form.
    static var minWidth: CGFloat { 480 }

    let phase: ResultsPhase
    @Binding var showsLog: Bool
    let logLines: [LogLine]
    let logHolder: LogViewHolder
    let onClearLog: () -> Void
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(spacing: 0) {
            switch phase {
            case .content(let header):
                VStack(spacing: 0) {
                    headerRow(header)
                    content()
                }
                .frame(maxHeight: .infinity)
            case .startingUp(let label, let status):
                startingUp(label: label, status: status)
            case .message(let title, let detail):
                message(title: title, detail: detail)
            case .idle(let label):
                if !showsLog {
                    Spacer()
                    Text(label)
                        .font(Theme.Typography.subheadline)
                        .foregroundStyle(Theme.Text.tertiary)
                    Spacer()
                }
            }

            if showsLog {
                LogOutputView(lines: logLines, holder: logHolder, onClear: onClearLog)
            }

            bottomBar
        }
        .frame(minWidth: Self.minWidth)
    }

    private func headerRow(_ header: ResultsHeader) -> some View {
        HStack(spacing: Theme.Space.md) {
            Image(systemName: header.icon)
                .foregroundStyle(Theme.Text.secondary)
            Text(header.title)
                .font(Theme.Typography.subheadlineMedium)
                .foregroundStyle(Theme.Text.secondary)
            Spacer()
            if let count = header.count {
                Text(count)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Text.tertiary)
            }
        }
        .padding(.horizontal, Theme.Space.xxl)
        .padding(.vertical, Theme.Space.md)
    }

    private func startingUp(label: String, status: String?) -> some View {
        VStack(spacing: Theme.Space.xl) {
            Spacer()
            ProgressView()
                .controlSize(.small)
            Text(label)
                .font(Theme.Typography.subheadline)
                .foregroundStyle(Theme.Text.secondary)
            if let status {
                Text(status)
                    .font(Theme.Typography.captionMono)
                    .foregroundStyle(Theme.Text.tertiary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Theme.Space.page)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func message(title: String, detail: String) -> some View {
        VStack(spacing: Theme.Space.md) {
            Spacer()
            Text(title)
                .font(Theme.Typography.subheadline)
                .foregroundStyle(Theme.Text.secondary)
            Text(detail)
                .font(Theme.Typography.captionMono)
                .foregroundStyle(Theme.Text.tertiary)
                .textSelection(.enabled)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.Space.page)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var bottomBar: some View {
        HStack {
            Button {
                withAnimation { showsLog.toggle() }
            } label: {
                Image(systemName: "terminal")
                    .foregroundStyle(showsLog ? Theme.Text.primary : Theme.Text.secondary)
            }
            .buttonStyle(.borderless)
            .help(showsLog ? Strings.Workflow.hideLogOutputHelp : Strings.Workflow.showLogOutputHelp)
            Spacer()
        }
        .padding(.horizontal, Theme.Space.xxl)
        .padding(.vertical, Theme.Space.md)
    }
}
