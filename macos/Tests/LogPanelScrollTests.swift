import XCTest
import AppKit
@testable import Jetlag

/// The log panel is a terminal transcript the user reads while a run streams into it.
/// Opening it must land on the newest line and keep up with the run; closing and
/// reopening it must come back to the line the user was reading, not to the top and not
/// to the tail they had deliberately scrolled away from.
final class LogPanelScrollTests: XCTestCase {

    private func line(_ i: Int) -> LogLine {
        LogLine(text: "2026-08-30 12:00:00  processing file number \(i) of a Korea import",
                stream: .stderr)
    }

    private func isAtBottom(_ scrollView: NSScrollView) -> Bool {
        TableTailFollowing.isAtBottom(
            visibleMaxY: scrollView.contentView.documentVisibleRect.maxY,
            documentHeight: scrollView.documentView?.frame.height ?? 0)
    }

    private func scrollOffset(_ scrollView: NSScrollView) -> CGFloat {
        scrollView.contentView.bounds.origin.y
    }

    /// Opening the log for the first time while a run is streaming shows the newest
    /// output, and every line appended afterwards keeps it in view.
    func testFirstOpenLandsAtTheEndAndFollowsAppends() throws {
        let state = AppState()
        let (host, _) = HostedWindow.make(state)

        state.logOutput = (0..<400).map(line)
        HostedWindow.settle(host)
        XCTAssertNil(HostedWindow.logScrollView(in: host), "the log is closed until toggled on")

        state.showLogOutput = true
        HostedWindow.settle(host)

        let scrollView = try XCTUnwrap(HostedWindow.logScrollView(in: host))
        XCTAssertGreaterThan(
            scrollOffset(scrollView), 0,
            "a first open must not sit at the top of a transcript the run has already filled")
        XCTAssertTrue(isAtBottom(scrollView), "a first open must land on the newest line")

        state.logOutput.append(contentsOf: (400..<500).map(line))
        HostedWindow.settle(host)
        XCTAssertTrue(isAtBottom(scrollView), "an open log must follow the lines a run appends")
    }

    /// Closing the log to see the Files table and reopening it returns the user to the
    /// line they were reading.
    func testReopeningTheLogRestoresTheScrollPosition() throws {
        let state = AppState()
        state.showLogOutput = true
        let (host, _) = HostedWindow.make(state)

        state.logOutput = (0..<400).map(line)
        HostedWindow.settle(host)

        let scrollView = try XCTUnwrap(HostedWindow.logScrollView(in: host))
        let documentHeight = try XCTUnwrap(scrollView.documentView).frame.height
        let midOffset = (documentHeight / 2).rounded()
        scrollView.contentView.scroll(to: NSPoint(x: 0, y: midOffset))
        scrollView.reflectScrolledClipView(scrollView.contentView)
        HostedWindow.settle(host)
        XCTAssertEqual(scrollOffset(scrollView), midOffset, accuracy: 1)

        state.showLogOutput = false
        HostedWindow.settle(host)
        XCTAssertNil(HostedWindow.logScrollView(in: host), "a closed log hosts no view")

        state.showLogOutput = true
        HostedWindow.settle(host)

        let reopened = try XCTUnwrap(HostedWindow.logScrollView(in: host))
        XCTAssertEqual(
            scrollOffset(reopened), midOffset, accuracy: 1,
            "reopening must restore where the user was reading, not the top or the tail")
    }

    /// A user reading back through the log is not yanked to the newest line by the run
    /// appending more output.
    func testAppendedLinesDoNotMoveAViewTheUserScrolledUp() throws {
        let state = AppState()
        state.showLogOutput = true
        let (host, _) = HostedWindow.make(state)

        state.logOutput = (0..<400).map(line)
        HostedWindow.settle(host)

        let scrollView = try XCTUnwrap(HostedWindow.logScrollView(in: host))
        let midOffset = (try XCTUnwrap(scrollView.documentView).frame.height / 2).rounded()
        scrollView.contentView.scroll(to: NSPoint(x: 0, y: midOffset))
        scrollView.reflectScrolledClipView(scrollView.contentView)
        HostedWindow.settle(host)

        state.logOutput.append(contentsOf: (400..<500).map(line))
        HostedWindow.settle(host)

        XCTAssertEqual(scrollOffset(scrollView), midOffset, accuracy: 1)
        XCTAssertFalse(isAtBottom(scrollView))
    }
}
