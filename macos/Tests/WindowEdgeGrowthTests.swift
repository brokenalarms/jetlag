import XCTest
@testable import Jetlag

/// Opening the panel used to be the only thing that grew the window to the screen
/// edge, so a second run started with the panel already open left the window narrow
/// and the table clipped. These tests pin `WindowEdgeGrowth.targetFrame` as a pure
/// function of the panel/run transitions, independent of any window or screen.
final class WindowEdgeGrowthTests: XCTestCase {
    private let frame = CGRect(x: 100, y: 100, width: 900, height: 700)
    private let screenEdge: CGFloat = 2000

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
}
