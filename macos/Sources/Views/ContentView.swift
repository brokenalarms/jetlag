import SwiftUI

struct ContentView: View {
    @Bindable var state: AppState

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
        .toolbar(removing: .sidebarToggle)
    }
}
