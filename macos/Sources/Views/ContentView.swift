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
                WorkflowDetail(state: state)
            case .profiles:
                ProfilesView(state: state)
            }
        }
    }
}

/// The workflow form beside its files/log panel.
///
/// The form is a fixed-width column of controls and the panel is the only thing that
/// flexes, so a plain `HStack` is the whole layout: the form gets exactly the width it
/// declares and the panel takes every remaining point. The stack's minimum is derived
/// from its children — the form's width plus the panel's minimum when the panel is open
/// — which is what `windowResizability(.contentMinSize)` turns into a wider window when
/// the panel opens. A split view would add a draggable divider, but the form cannot
/// resize, so there is nothing for one to do; it would also report no minimum of its own.
struct WorkflowDetail: View {
    @Bindable var state: AppState

    var body: some View {
        HStack(spacing: 0) {
            WorkflowView(state: state)
            if state.showInspector {
                Divider()
                InspectorPanel(state: state)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}
