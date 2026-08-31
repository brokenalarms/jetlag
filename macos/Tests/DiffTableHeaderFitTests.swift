import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The Files table's header divider behaves the way a macOS table header is expected
/// to: hovering a divider gives the resize cursor without a click first, and
/// double-clicking one snaps that column to the width that shows its widest cell
/// untruncated — past the auto-fit cap the column is otherwise held to, and back out
/// again after the user has dragged the column narrow.
final class DiffTableHeaderFitTests: XCTestCase {

    private let mono = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
    private let detail = NSFont.systemFont(ofSize: 9)

    private func width(_ text: String, _ font: NSFont) -> CGFloat {
        (text as NSString).size(withAttributes: [.font: font]).width
    }

    /// A click recognizer whose reported location the test supplies: the header's
    /// action reads `location(in:)`, which only a real mouse event would otherwise
    /// fill in. Everything else — the target, the action, the header it is attached
    /// to — is the app's own.
    private final class StubHeaderClick: NSClickGestureRecognizer {
        var stubbedLocation: NSPoint = .zero
        override func location(in view: NSView?) -> NSPoint { stubbedLocation }
    }

    private func allViews<T: NSView>(of type: T.Type, in view: NSView) -> [T] {
        var found: [T] = []
        if let match = view as? T { found.append(match) }
        for subview in view.subviews { found += allViews(of: type, in: subview) }
        return found
    }

    private func stream(_ count: Int, into state: AppState,
                        staleFields: [String], fileName: (Int) -> String) {
        let fields = staleFields.map { "\"\($0)\"" }.joined(separator: ", ")
        for i in 0..<count {
            let file = fileName(i)
            let lines = [
                #"{"event": "pipeline_file", "file": "\#(file)"}"#,
                #"{"event": "timestamp_result", "file": "\#(file)", "action": "would_fix", "original_time": "2025:08:15 14:08:5\#(i % 10)+09:00", "corrected_time": "2025:08:15 14:08:5\#(i % 10)+09:00", "source": "datetimeoriginal", "timezone": "+09:00", "correction_mode": "timezone", "original_epoch": \#(1755000000 + i * 60).0, "corrected_epoch": \#(1755000000 + i * 60).0, "requires_force_timezone": false, "stale_fields": [\#(fields)]}"#,
                #"{"event": "organize_result", "file": "\#(file)", "action": "skipped", "dest": "/Volumes/Media/Ready/2025/2025-08-15/\#(file)", "reason": "exists_differs"}"#,
                #"{"event": "pipeline_result", "file": "\#(file)", "result": "would_change"}"#,
            ]
            for line in lines {
                state.appendLog(LogLine(text: line, stream: .stdout))
                RunLoop.main.run(until: Date())
            }
        }
    }

    /// The panel shows its empty state until the first row arrives, so the table is
    /// located after streaming, not before.
    private func host(_ state: AppState) -> NSHostingView<WorkflowDetail> {
        let host = NSHostingView(rootView: WorkflowDetail(state: state))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1900, height: 800),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 1900, height: 800)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        return host
    }

    private func table(in host: NSView) throws -> NSTableView {
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        host.layoutSubtreeIfNeeded()
        return try XCTUnwrap(
            allViews(of: NSTableView.self, in: host).first { $0.tableColumns.count == 7 },
            "no seven-column NSTableView hosted")
    }

    private func installedDoubleClick(on table: NSTableView) throws -> NSClickGestureRecognizer {
        let header = try XCTUnwrap(table.headerView, "the table has no header view")
        return try XCTUnwrap(
            header.gestureRecognizers.compactMap { $0 as? NSClickGestureRecognizer }
                .first { $0.numberOfClicksRequired == 2 },
            "the Files table's header must carry the double-click-to-fit recognizer")
    }

    /// Runs the header's own double-click action at the right edge of the given
    /// column, as a real double-click on that divider would.
    private func doubleClickDivider(ofColumn index: Int, in table: NSTableView) throws {
        let installed = try installedDoubleClick(on: table)
        let header = try XCTUnwrap(table.headerView)
        let stub = StubHeaderClick()
        stub.stubbedLocation = NSPoint(x: table.rect(ofColumn: index).maxX, y: 0)
        header.addGestureRecognizer(stub)
        defer { header.removeGestureRecognizer(stub) }
        let target = try XCTUnwrap(installed.target as AnyObject?, "the recognizer has no target")
        let action = try XCTUnwrap(installed.action, "the recognizer has no action")
        _ = target.perform(action, with: stub)
    }

    /// A click recognizer delays the primary mouse button by default, which holds the
    /// mouse-down back from the header itself — so the divider's resize cursor and
    /// drag only engage after a first, discarded click. The fit recognizer must not
    /// delay those events: its action fires on the second click regardless.
    func testHeaderDoubleClickRecognizerDoesNotDelayPrimaryMouseEvents() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let hosted = host(state)
        stream(3, into: state, staleFields: ["Keys:CreationDate"]) { "DJI_000\($0).MP4" }
        let table = try table(in: hosted)

        let gesture = try installedDoubleClick(on: table)

        XCTAssertFalse(gesture.delaysPrimaryMouseButtonEvents,
                       "the header must keep receiving mouse-downs so the divider tracks on hover")
    }

    /// The action and status columns are capped so a long writes subtitle cannot
    /// stretch them; double-clicking their divider is how the user sees the full
    /// text, so it must expand past that cap to the measured width of the subtitle.
    func testDoubleClickExpandsACappedColumnToItsFullContentWidth() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let hosted = host(state)
        let fields = ["Keys:CreationDate", "QuickTime:CreateDate",
                      "QuickTime:TrackCreateDate", "QuickTime:MediaCreateDate"]
        stream(3, into: state, staleFields: fields) { "DJI_000\($0).MP4" }
        let table = try table(in: hosted)

        let subtitle = Strings.DiffTable.wouldWrite(fields.joined(separator: ", "))
        let subtitleWidth = width(subtitle, detail)
        XCTAssertGreaterThan(subtitleWidth, DiffTableView.writesColumnMaxWidth,
                             "the fixture must exceed the cap for the expansion to mean anything")
        XCTAssertLessThanOrEqual(table.tableColumns[4].width, DiffTableView.writesColumnMaxWidth,
                                 "the action column starts held to the auto-fit cap")

        try doubleClickDivider(ofColumn: 4, in: table)

        XCTAssertGreaterThanOrEqual(
            table.tableColumns[4].width, subtitleWidth,
            "double-clicking the divider must fit the whole writes subtitle, not the capped width")
    }

    /// After the user drags a column narrow, double-clicking its divider snaps it
    /// back to the full content width — not to the capped width the auto-fitter holds
    /// it to, which for a long filename still truncates.
    func testDoubleClickAfterAManualDragRestoresTheFullContentWidth() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let hosted = host(state)
        let long = String(repeating: "VeryLongCameraFileName_", count: 5) + "0001.insv"
        stream(3, into: state, staleFields: ["Keys:CreationDate"]) { _ in long }
        let table = try table(in: hosted)

        let nameWidth = width(long, mono)
        XCTAssertGreaterThan(nameWidth, DiffTableView.fileColumnMaxWidth,
                             "the fixture must exceed the filename cap")

        table.tableColumns[0].width = 90
        XCTAssertEqual(table.tableColumns[0].width, 90, accuracy: 1)

        try doubleClickDivider(ofColumn: 0, in: table)

        XCTAssertGreaterThanOrEqual(
            table.tableColumns[0].width, nameWidth,
            "double-clicking after a drag must fit the whole filename, not the capped width")
    }
}
