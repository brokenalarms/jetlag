import AppKit
import SwiftUI

/// The panel is the column that wants space; opening it or starting a run is the moment
/// it needs it. `targetFrame` grows the window's right edge to the screen's visible edge
/// on either transition, never past it and never when the window is already there — a
/// pure function so the transition logic is testable without AppKit.
enum WindowEdgeGrowth {
    /// Past sidebar + form + the panel's own cap the window would hold only empty
    /// desktop, so growth stops there as it stops at the screen edge.
    static let contentMaxWidth = ContentView.sidebarWidth + WorkflowView.formWidth + WorkflowDetail.panelMaxWidth

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

    /// How long the window takes to reach the target frame. AppKit's own default, and
    /// stated rather than inherited: a group started while another animation context is
    /// current takes that context's duration, and at zero the animator applies the frame
    /// immediately — synchronously, in the middle of the SwiftUI render this is called
    /// from, which is exactly what `grow` exists to avoid.
    static let growthDuration: TimeInterval = 0.25

    /// Schedules the resize on the window's animator and returns; the frame arrives
    /// when the animation group finishes.
    ///
    /// `setFrame(_:display:animate:)` would animate it synchronously instead: it blocks
    /// and re-lays-out the window's content once per animation frame. Growth is decided
    /// from `updateNSView`, which SwiftUI runs while it is rendering the `NSHostingView`
    /// that contains the controller, so that synchronous layout is reentrant — every
    /// pass it lands in is dropped ("NSHostingView is being laid out reentrantly"),
    /// taking the AttributeGraph through cycles for the whole animation. The animator
    /// proxy runs no AppKit layout inside SwiftUI's update, and the visible resize is
    /// the same.
    ///
    /// The animator holds the frame back only while it has an animation to run: a window
    /// it declines to animate — one that is not on screen — is resized outright, inside
    /// the render pass. Such a window has no edge to grow toward and nobody watching it,
    /// so the controller does not call this for one.
    static func grow(_ window: NSWindow, to target: CGRect, completion: (() -> Void)? = nil) {
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = growthDuration
            window.animator().setFrame(target, display: true)
        }, completionHandler: completion)
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
        // A window that is not on screen has no visible edge to grow toward, and the
        // animator resizes it synchronously — reentrant layout, from inside this update.
        guard let window = view.window, window.isVisible, let screen = window.screen else { return }
        guard let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: coordinator.previousPanelOpen,
            panelOpen: panelOpen,
            previousIsRunning: coordinator.previousIsRunning,
            isRunning: isRunning,
            frame: window.frame,
            screenEdge: screen.visibleFrame.maxX,
            maxWidth: WindowEdgeGrowth.contentMaxWidth
        ) else { return }
        WindowEdgeGrowth.grow(window, to: target)
    }
}
