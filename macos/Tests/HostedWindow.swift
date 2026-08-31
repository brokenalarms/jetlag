import AppKit
import SwiftUI
@testable import Jetlag

/// Hosts `ContentView` for tests that need the panel's AppKit views at a real size —
/// scroll offsets, column widths, anything decided during layout rather than in a model.
enum HostedWindow {
    /// Laid out but never ordered on screen: a test host that appears over the user's
    /// desktop while the suite streams synthetic rows is a real window to the user.
    /// Layout runs the same without it.
    static func make(
        _ state: AppState,
        size: NSSize = NSSize(width: 1400, height: 800)
    ) -> (host: NSHostingView<ContentView>, window: NSWindow) {
        state.selectedTab = .workflow
        state.showInspector = true
        let host = NSHostingView(rootView: ContentView(state: state))
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        settle(host)
        return (host, window)
    }

    /// Gives SwiftUI's observation a turn of the run loop to apply a state change, then
    /// lays the result out — the point at which the hosted AppKit views get their size.
    static func settle(_ host: NSView, for interval: TimeInterval = 0.2) {
        RunLoop.main.run(until: Date().addingTimeInterval(interval))
        host.layoutSubtreeIfNeeded()
    }

    /// The log's scroll view, found by what it holds rather than by its type, so the
    /// search reports whichever instance the panel currently hosts — or nothing, when the
    /// log is closed. The Files table's scroll view holds an `NSTableView` instead.
    static func logScrollView(in view: NSView) -> NSScrollView? {
        if let scrollView = view as? NSScrollView, scrollView.documentView is NSTextView {
            return scrollView
        }
        for subview in view.subviews {
            if let found = logScrollView(in: subview) { return found }
        }
        return nil
    }
}
