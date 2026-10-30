import SwiftUI

struct InspectorPanel: View {
    @Bindable var state: AppState

    static let minWidth = ResultsPanel<DiffTableView>.minWidth

    var body: some View {
        ResultsPanel(phase: phase,
                     showsLog: $state.showLogOutput,
                     logLines: state.logOutput,
                     logHolder: state.logViewHolder,
                     onClearLog: { state.clearLog() }) {
            DiffTableView(rows: state.visibleRows)
        }
    }

    private var phase: ResultsPhase {
        if state.isRunning && state.visibleRows.isEmpty {
            return .startingUp(label: Strings.Workflow.inspectorStartingLabel,
                               status: state.latestStatusLine)
        }
        if !state.visibleRows.isEmpty {
            return .content(ResultsHeader(icon: "tablecells", title: Strings.DiffTable.title,
                                          count: Strings.DiffTable.fileCount(state.visibleRows.count)))
        }
        if let empty = state.emptySource {
            return .message(title: Strings.Workflow.inspectorNoMediaLabel(extensions: empty.extensions),
                            detail: empty.source)
        }
        return .idle(label: Strings.Workflow.inspectorEmptyLabel)
    }
}
