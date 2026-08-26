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
        // The window's resizable range is the content's own: with the panel closed the
        // content has one width (sidebar + form) and so does the window; opening the
        // panel raises the minimum by the panel's minimum and removes the maximum, so the
        // window grows to the right and only the panel can be widened from there. No
        // width is declared anywhere for this — it is derived from the views.
        .windowResizability(.contentSize)
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
