import SwiftUI

@main
struct JetlagApp: App {
    @State private var state = AppState()

    init() {
        // Utility apps don't benefit from automatic window tabbing
        NSWindow.allowsAutomaticWindowTabbing = false
    }

    /// The unit tests run inside the app: whatever is in the profile sources on
    /// the Mac running them must not reach their state.
    private static let isTestHost = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil

    private func scanProfileSourcesUnlessTesting() async {
        guard !Self.isTestHost else { return }
        await state.scanProfileSources()
    }

    var body: some Scene {
        WindowGroup {
            ContentView(state: state)
                .onAppear { state.loadProfiles() }
                .task { await state.refreshGyroflowStatus() }
                .task { await scanProfileSourcesUnlessTesting() }
                .onReceive(NSWorkspace.shared.notificationCenter.publisher(for: NSWorkspace.didMountNotification)) { _ in
                    Task { await scanProfileSourcesUnlessTesting() }
                }
                .onReceive(NSWorkspace.shared.notificationCenter.publisher(for: NSWorkspace.didUnmountNotification)) { _ in
                    Task { await scanProfileSourcesUnlessTesting() }
                }
        }
        // The window's resizable range is the content's own: with the panel closed the
        // content has one width (sidebar + form) and so does the window; opening the
        // panel raises the minimum by the panel's minimum and removes the maximum, so the
        // window grows to the right and only the panel can be widened from there. No
        // width is declared anywhere for this — it is derived from the views.
        .windowResizability(.contentSize)
        // The height, unlike the width, is not the content's: the form's steps scroll,
        // so the window opens at a default height and the user resizes it from there.
        .defaultSize(width: ContentView.sidebarWidth + WorkflowView.formWidth, height: ContentView.defaultHeight)
        // ContentView is a plain HStack, not a NavigationSplitView (see ContentView's own
        // doc comment for why), so the titlebar knows nothing about the sidebar column and
        // draws the navigationTitle left-aligned after the traffic lights — straddling the
        // sidebar/detail seam at the sidebar's width. Hiding the title text leaves the
        // navigationTitle in place for Mission Control, the Window menu and accessibility.
        .windowToolbarStyle(.unifiedCompact(showsTitle: false))
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
