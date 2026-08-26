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
            .navigationSplitViewColumnWidth(
                min: SplitViewLayout.sidebarMinWidth,
                ideal: SplitViewLayout.sidebarIdealWidth
            )
        } detail: {
            Group {
                switch state.selectedTab {
                case .workflow:
                    WorkflowView(state: state)
                case .profiles:
                    ProfilesView(state: state)
                }
            }
            // Min and ideal are the same and there is no maximum: the detail column
            // needs exactly enough room for the form, so the split view has one answer
            // to settle on and the inspector takes everything left over.
            .navigationSplitViewColumnWidth(
                min: SplitViewLayout.detailMinWidth,
                ideal: SplitViewLayout.detailMinWidth
            )
        }
        .inspector(isPresented: inspectorPresented) {
            InspectorPanel(state: state)
                .inspectorColumnWidth(
                    min: SplitViewLayout.inspectorMinWidth,
                    ideal: SplitViewLayout.inspectorIdealWidth
                )
        }
        // The window's minimum tracks what is actually on screen, so opening the
        // inspector pushes the window's right edge out instead of stealing width from
        // the sidebar and form. `windowResizability(.contentMinSize)` is what acts on it.
        .frame(
            minWidth: SplitViewLayout.windowMinWidth(inspectorVisible: inspectorPresented.wrappedValue),
            minHeight: SplitViewLayout.windowMinHeight
        )
    }
}
