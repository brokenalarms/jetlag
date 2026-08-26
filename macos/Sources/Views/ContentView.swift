import SwiftUI

/// Sidebar, form and (when open) panel side by side.
///
/// A plain `HStack`, not a `NavigationSplitView`: a split view fills whatever window it is
/// given and centres narrower content in its detail column, so the window could never
/// size itself to the form. Here every child declares its own width or flexibility and
/// nothing else — the sidebar its width, the form its width, the panel its minimum — and
/// SwiftUI derives the content's size range from them. With
/// `windowResizability(.contentSize)` the window follows that range: exactly sidebar +
/// form with the panel closed; growing to the right, panel only, with it open.
struct ContentView: View {
    @Bindable var state: AppState

    /// The sidebar's one design width: a two-item list has no intrinsic width of its own.
    static let sidebarWidth: CGFloat = 160

    var body: some View {
        HStack(spacing: 0) {
            List(SidebarTab.allCases, selection: $state.selectedTab) { tab in
                Label(tab.label, systemImage: tab.systemImage)
                    .tag(tab)
            }
            .listStyle(.sidebar)
            .frame(width: Self.sidebarWidth)
            Divider()
            switch state.selectedTab {
            case .workflow:
                WorkflowDetail(state: state)
            case .profiles:
                ProfilesView(state: state)
            }
        }
        .background(WindowEdgeGrowthController(panelOpen: state.showInspector, isRunning: state.isRunning))
    }
}
