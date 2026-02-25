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
                .frame(minWidth: 900, minHeight: 500)
                .onAppear { loadProfiles() }
        }
        .defaultSize(width: 1050, height: 720)
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
                .onDisappear { loadProfiles() }
        }
    }

    private func loadProfiles() {
        do {
            state.profilesConfig = try ProfileService.load(from: state.resolvedProfilesPath)
            state.profileLoadError = nil
        } catch {
            state.profilesConfig = nil
            state.profileLoadError = error
        }
    }
}
