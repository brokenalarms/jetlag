import SwiftUI

@main
struct TimcopApp: App {
    @State private var state = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView(state: state)
                .frame(minWidth: 700, minHeight: 500)
                .onAppear { loadProfiles() }
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
