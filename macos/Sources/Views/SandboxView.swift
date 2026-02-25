import SwiftUI

/// Standalone playground view with its own NavigationSplitView.
/// Swap into JetlagApp's WindowGroup in place of ContentView to experiment.
///
///     WindowGroup {
///         SandboxView()
///             .frame(minWidth: 900, minHeight: 500)
///     }
struct SandboxView: View {
    @State private var selectedItem: String? = "Canvas"

    private let items = ["Canvas"]

    var body: some View {
        NavigationSplitView {
            List(items, id: \.self, selection: $selectedItem) { item in
                Label(item, systemImage: "hammer")
                    .tag(item)
            }
            .navigationSplitViewColumnWidth(min: 140, ideal: 160)
        } detail: {
            if let selectedItem {
                switch selectedItem {
                case "Canvas":
                    canvas
                default:
                    Text("Select an item")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Experiments go here

    private var canvas: some View {
        VStack {
            Text("Sandbox")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle("Canvas")
    }
}
