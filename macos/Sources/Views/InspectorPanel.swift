import SwiftUI

struct InspectorPanel: View {
    @Bindable var state: AppState

    /// The narrowest the files table is still readable at. Declaring it here is what makes
    /// opening the panel widen the window: the window's minimum grows by this amount, so
    /// AppKit extends the right edge instead of squeezing the form.
    static let minWidth: CGFloat = 480

    var body: some View {
        VStack(spacing: 0) {
            if state.isRunning && state.visibleRows.isEmpty {
                startingUp
            } else if !state.visibleRows.isEmpty {
                DiffTableView(rows: state.visibleRows)
            } else if let empty = state.emptySource {
                noMediaFiles(empty)
            } else if !state.showLogOutput {
                Spacer()
                Text(Strings.Workflow.inspectorEmptyLabel)
                    .font(Theme.Typography.subheadline)
                    .foregroundStyle(Theme.Text.tertiary)
                Spacer()
            }

            if state.showLogOutput {
                LogOutputView(
                    lines: state.logOutput,
                    holder: state.logViewHolder,
                    onClear: { state.clearLog() })
            }

            bottomBar
        }
        .frame(minWidth: Self.minWidth)
    }

    /// Scanning a card takes a while before the first file lands in the table.
    /// Without the pipeline's own progress lines this reads as a hang.
    private var startingUp: some View {
        VStack(spacing: Theme.Space.xl) {
            Spacer()
            ProgressView()
                .controlSize(.small)
            Text(Strings.Workflow.inspectorStartingLabel)
                .font(Theme.Typography.subheadline)
                .foregroundStyle(Theme.Text.secondary)
            if let status = state.latestStatusLine {
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

    /// A run over a source with nothing the profile matches has no rows to show,
    /// and the never-run placeholder would read as the run not having happened.
    private func noMediaFiles(_ empty: EmptySource) -> some View {
        VStack(spacing: Theme.Space.md) {
            Spacer()
            Text(Strings.Workflow.inspectorNoMediaLabel(extensions: empty.extensions))
                .font(Theme.Typography.subheadline)
                .foregroundStyle(Theme.Text.secondary)
            Text(empty.source)
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
                withAnimation { state.showLogOutput.toggle() }
            } label: {
                Image(systemName: "terminal")
                    .foregroundStyle(state.showLogOutput ? Theme.Text.primary : Theme.Text.secondary)
            }
            .buttonStyle(.borderless)
            .help(state.showLogOutput ? Strings.Workflow.hideLogOutputHelp : Strings.Workflow.showLogOutputHelp)
            Spacer()
        }
        .padding(.horizontal, Theme.Space.xxl)
        .padding(.vertical, Theme.Space.md)
    }
}
