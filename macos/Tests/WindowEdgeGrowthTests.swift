import XCTest
import AppKit
import CoreGraphics
import SwiftUI
@testable import Jetlag

/// Opening the panel used to be the only thing that grew the window to the screen
/// edge, so a second run started with the panel already open left the window narrow
/// and the table clipped. These tests pin `WindowEdgeGrowth.targetFrame` as a pure
/// function of the panel/run transitions, independent of any window or screen, and
/// pin how the resulting frame is applied: scheduled on the window's animator, never
/// animated synchronously inside the SwiftUI update that decides it.
final class WindowEdgeGrowthTests: XCTestCase {
    private let frame = CGRect(x: 100, y: 100, width: 900, height: 700)
    private let screenEdge: CGFloat = 2000

    /// The window server drives window frame animations, and stops driving them while
    /// the screen is locked: the group is entered and the animator holds the frame, but
    /// the timeline never advances and the completion never runs. What the scheduling
    /// tests below assert before the wait still holds there; only the frame's arrival
    /// cannot be observed, so those halves are skipped rather than read as a failure.
    private var screenIsLocked: Bool {
        guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
        return (session["CGSSessionScreenIsLocked"] as? NSNumber)?.boolValue == true
    }

    /// AC 2: opening the panel grows the window's right edge to the screen edge.
    func testGrowsOnPanelOpenTransition() {
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: frame, screenEdge: screenEdge
        )
        XCTAssertEqual(target?.maxX, screenEdge)
        XCTAssertEqual(target?.minX, frame.minX, "the left edge must not move")
        XCTAssertEqual(target?.height, frame.height, "only the width changes")
    }

    /// AC 1: a run starting with the panel already open still grows the window — the
    /// bug this bead fixes, since the panel had no false→true transition to react to.
    func testGrowsOnRunStartWithPanelAlreadyOpen() {
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: true, panelOpen: true,
            previousIsRunning: false, isRunning: true,
            frame: frame, screenEdge: screenEdge
        )
        XCTAssertEqual(target?.maxX, screenEdge)
    }

    /// AC 3: never resizes past the screen edge, and never when already there.
    func testNoOpWhenAlreadyAtTheScreenEdge() {
        let atEdge = CGRect(x: 100, y: 100, width: screenEdge - 100, height: 700)
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: atEdge, screenEdge: screenEdge
        )
        XCTAssertNil(target)
    }

    /// AC 3: idle updates — neither the panel nor the run state changed — never resize
    /// the window, even with the panel open and room left on screen.
    func testNoOpOnIdleUpdates() {
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: true, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: frame, screenEdge: screenEdge
        )
        XCTAssertNil(target)
    }

    /// The panel must actually be open for growth to matter — a run starting while the
    /// panel is closed has nothing to give the extra room to.
    func testNoOpOnRunStartWithPanelClosed() {
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: false,
            previousIsRunning: false, isRunning: true,
            frame: frame, screenEdge: screenEdge
        )
        XCTAssertNil(target)
    }

    /// The content's own maximum bounds the growth as the screen edge does: with a
    /// panel capped at twice sidebar + form, the window stops at that width even when
    /// the screen has room, and never grows at all once it is already there.
    func testGrowthStopsAtTheContentMaximum() {
        let target = WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: frame, screenEdge: screenEdge, maxWidth: 1500
        )
        XCTAssertEqual(target?.maxX, frame.minX + 1500)

        let atCap = CGRect(x: 100, y: 100, width: 1500, height: 700)
        XCTAssertNil(WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: atCap, screenEdge: screenEdge, maxWidth: 1500
        ))
    }

    // MARK: - Applying the frame

    /// The controller decides growth from `updateNSView`, which SwiftUI runs while it
    /// is rendering the hosting view the controller lives in. A synchronous
    /// `setFrame(_:display:animate:)` there blocks and re-lays-out that hosting view
    /// once per animation frame, so every SwiftUI layout pass it lands in is dropped.
    /// Hosting the controller in a real window and driving panel open proves the resize
    /// is scheduled rather than applied: the window is still at its original frame when
    /// the update returns, and reaches the target once the scheduled animation has run.
    func testPanelOpenSchedulesTheResizeInsteadOfApplyingItDuringTheUpdate() throws {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 500),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        // On screen, as the app's window is: the controller only grows a visible window,
        // and only for a visible window does the animator animate rather than resize
        // outright.
        window.orderFrontRegardless()
        defer { window.orderOut(nil) }
        let host = NSHostingView(rootView: GrowthProbe(panelOpen: false))
        window.contentView = host
        host.layoutSubtreeIfNeeded()

        let original = window.frame
        let screen = try XCTUnwrap(window.screen)
        let expected = try XCTUnwrap(WindowEdgeGrowth.targetFrame(
            previousPanelOpen: false, panelOpen: true,
            previousIsRunning: false, isRunning: false,
            frame: original, screenEdge: screen.visibleFrame.maxX,
            maxWidth: WindowEdgeGrowth.contentMaxWidth
        ), "the test window must have room left to grow into for this to prove anything")

        let grown = expectation(description: "the window reaches the target frame")
        grown.assertForOverFulfill = false
        let observer = NotificationCenter.default.addObserver(
            forName: NSWindow.didResizeNotification, object: window, queue: nil
        ) { _ in
            if window.frame == expected { grown.fulfill() }
        }
        defer { NotificationCenter.default.removeObserver(observer) }

        host.rootView = GrowthProbe(panelOpen: true)
        host.layoutSubtreeIfNeeded()
        XCTAssertEqual(window.frame, original,
                       "the update must schedule the resize, not animate it synchronously mid-render")

        try XCTSkipIf(screenIsLocked, "window animations do not advance while the screen is locked")
        wait(for: [grown], timeout: 5)
        XCTAssertEqual(window.frame, expected, "the scheduled animation must land on the target frame")
    }

    /// `grow` is the whole of how a target frame is applied: it hands the frame to the
    /// window's animator inside an animation group and returns with the window
    /// untouched, and that group's completion runs with the target frame in place.
    func testGrowAppliesTheFrameThroughTheAnimationGroupsCompletion() throws {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 500),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.orderFrontRegardless()
        defer { window.orderOut(nil) }
        let original = window.frame
        var target = original
        target.size.width = original.width + 500

        let finished = expectation(description: "the animation group completes")
        var frameAtCompletion = CGRect.zero
        WindowEdgeGrowth.grow(window, to: target) {
            frameAtCompletion = window.frame
            finished.fulfill()
        }
        XCTAssertEqual(window.frame, original, "the animator must not apply the frame synchronously")

        try XCTSkipIf(screenIsLocked, "window animations do not advance while the screen is locked")
        wait(for: [finished], timeout: 5)
        XCTAssertEqual(frameAtCompletion, target)
    }

    /// A window that is not on screen has no visible edge to grow toward, and the
    /// animator resizes such a window outright rather than animating it — synchronously,
    /// inside the render pass `updateNSView` runs in. Opening the panel on a controller
    /// hosted in a window never ordered front must therefore do nothing at all: the frame
    /// stays where it was and no resize is ever scheduled.
    func testPanelOpenDoesNotGrowAWindowThatIsNotOnScreen() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 500),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: GrowthProbe(panelOpen: false))
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        XCTAssertFalse(window.isVisible, "the window must never be ordered on screen for this test")

        let original = window.frame
        let resized = expectation(description: "the window is resized")
        resized.isInverted = true
        let observer = NotificationCenter.default.addObserver(
            forName: NSWindow.didResizeNotification, object: window, queue: nil
        ) { _ in resized.fulfill() }
        defer { NotificationCenter.default.removeObserver(observer) }

        host.rootView = GrowthProbe(panelOpen: true)
        host.layoutSubtreeIfNeeded()
        XCTAssertEqual(window.frame, original, "an off-screen window must not be resized during the update")

        wait(for: [resized], timeout: 1)
        XCTAssertEqual(window.frame, original, "no growth may arrive later either")
    }
}

/// A host for the controller under test: nothing about the probe itself matters, so it
/// is a clear, fully flexible view carrying the controller exactly as `ContentView`
/// does — in its background, updated on every state change.
private struct GrowthProbe: View {
    var panelOpen: Bool

    var body: some View {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(WindowEdgeGrowthController(panelOpen: panelOpen, isRunning: false))
    }
}
