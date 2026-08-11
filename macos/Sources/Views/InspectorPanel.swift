import SwiftUI

struct InspectorPanel: View {
    @Bindable var state: AppState

    var body: some View {
        VStack(spacing: 0) {
            if state.isRunning && state.visibleRows.isEmpty {
                startingUp
            } else if !state.visibleRows.isEmpty {
                DiffTableView(rows: state.visibleRows)
            } else if !state.showLogOutput {
                Spacer()
                Text(Strings.Workflow.inspectorEmptyLabel)
                    .font(.subheadline)
                    .foregroundStyle(.tertiary)
                Spacer()
            }

            if state.showLogOutput {
                LogOutputView(lines: state.logOutput, onClear: { state.clearLog() })
            }

            bottomBar
        }
    }

    /// Scanning a card takes a while before the first file lands in the table.
    /// Without the pipeline's own progress lines this reads as a hang.
    private var startingUp: some View {
        VStack(spacing: 10) {
            Spacer()
            ProgressView()
                .controlSize(.small)
            Text(Strings.Workflow.inspectorStartingLabel)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let status = state.latestStatusLine {
                Text(status)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
            }
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
                    .foregroundStyle(state.showLogOutput ? .primary : .secondary)
            }
            .buttonStyle(.borderless)
            .help(state.showLogOutput ? Strings.Workflow.hideLogOutputHelp : Strings.Workflow.showLogOutputHelp)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }
}
