import SwiftUI

@main
struct JetlagApp: App {
    @State private var state = AppState()

    init() {
        // Utility apps don't benefit from automatic window tabbing
        NSWindow.allowsAutomaticWindowTabbing = false
    }

    var body: some Scene {
        WindowGroup {
            ContentView(state: state)
                .onAppear { state.loadProfiles() }
                .task { await state.refreshGyroflowStatus() }
        }
        // The window's minimum is whatever the content's minimum resolves to — the sidebar,
        // the form and (when open) the panel — so opening the panel grows the window and
        // AppKit keeps the result on screen. No width is declared anywhere for this.
        .windowResizability(.contentMinSize)
        .commands {
            // Single-window utility — no New Window or Open Recent
            CommandGroup(replacing: .newItem) {}
            // Sidebar is required navigation; don't let it be hidden
            CommandGroup(replacing: .sidebar) {}
            // No help bundle is shipped; suppress the broken Help menu item
            CommandGroup(replacing: .help) {}
        }

        Settings {
            SettingsView(state: state)
                .onDisappear { state.loadProfiles() }
        }
    }
}
