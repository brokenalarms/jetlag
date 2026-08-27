import AppKit
import SwiftUI

/// The panel is the column that wants space; opening it or starting a run is the moment
/// it needs it. `targetFrame` grows the window's right edge to the screen's visible edge
/// on either transition, never past it and never when the window is already there — a
/// pure function so the transition logic is testable without AppKit.
enum WindowEdgeGrowth {
    static func targetFrame(
        previousPanelOpen: Bool,
        panelOpen: Bool,
        previousIsRunning: Bool,
        isRunning: Bool,
        frame: CGRect,
        screenEdge: CGFloat,
        maxWidth: CGFloat = .infinity
    ) -> CGRect? {
        let panelJustOpened = !previousPanelOpen && panelOpen
        let runJustStarted = !previousIsRunning && isRunning
        // The content's own maximum (the panel's cap) bounds the growth as the screen
        // edge does: past it the window would only hold empty desktop.
        let edge = min(screenEdge, frame.minX + maxWidth)
        guard panelOpen, panelJustOpened || runJustStarted, frame.maxX < edge else { return nil }
        var target = frame
        target.size.width = edge - frame.minX
        return target
    }
}

/// Applies `WindowEdgeGrowth` to the hosting window whenever the panel or run state
/// changes, tracking the previous values itself so it can detect the false→true
/// transitions that matter. An invisible view rather than a modifier because it needs
/// the AppKit window, which only an `NSViewRepresentable` can reach.
struct WindowEdgeGrowthController: NSViewRepresentable {
    var panelOpen: Bool
    var isRunning: Bool

    final class Coordinator {
        var previousPanelOpen = false
        var previousIsRunning = false
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        NSView(frame: .zero)
    }

    func updateNSView(_ view: NSView, context: Context) {
        let coordinator = context.coordinator
        defer {
            coordinator.previousPanelOpen = panelOpen
            coordinator.previousIsRunning = isRunning
        }
        guard let window = view.window, let screen = window.screen else { return }
        guard let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: coordinator.previousPanelOpen,
            panelOpen: panelOpen,
            previousIsRunning: coordinator.previousIsRunning,
            isRunning: isRunning,
            frame: window.frame,
            screenEdge: screen.visibleFrame.maxX,
            maxWidth: ContentView.sidebarWidth + WorkflowView.formWidth + WorkflowDetail.panelMaxWidth
        ) else { return }
        window.setFrame(target, display: true, animate: true)
    }
}
