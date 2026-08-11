import SwiftUI

struct ContentView: View {
    @Bindable var state: AppState

    /// The inspector is a trailing column of the whole split view, so it is
    /// declared here rather than inside the detail column — nesting it there
    /// leaves the split view and the inspector renegotiating widths against
    /// fixed-width detail content, which AppKit aborts as a constraint loop
    /// when the window is resized.
    private var inspectorPresented: Binding<Bool> {
        Binding(
            get: { state.showInspector && state.selectedTab == .workflow },
            set: { state.showInspector = $0 }
        )
    }

    var body: some View {
        NavigationSplitView {
            List(SidebarTab.allCases, selection: $state.selectedTab) { tab in
                Label(tab.label, systemImage: tab.systemImage)
                    .tag(tab)
            }
            .navigationSplitViewColumnWidth(min: 140, ideal: 160)
        } detail: {
            switch state.selectedTab {
            case .workflow:
                WorkflowView(state: state)
            case .profiles:
                ProfilesView(state: state)
            }
        }
        .inspector(isPresented: inspectorPresented) {
            InspectorPanel(state: state)
                .inspectorColumnWidth(min: 480, ideal: 600)
        }
//        .toolbar(removing: .sidebarToggle)
    }
}
