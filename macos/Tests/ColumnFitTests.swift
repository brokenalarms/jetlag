import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// Every column fits its content once a run's rows have filled in — and rows do fill
/// in: the pipeline appends a sparse live row and completes it event by event before
/// finalising it. Measuring a row once by position (#185) left the columns sized to
/// the empty row; this test drives rows through the same event path the app uses and
/// checks the applied column widths against the widest text each column holds. Only
/// the filename column has a cap.
final class ColumnFitTests: XCTestCase {

    private let mono = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
    private let system = NSFont.systemFont(ofSize: 11)

    private func width(_ text: String, _ font: NSFont) -> CGFloat {
        (text as NSString).size(withAttributes: [.font: font]).width
    }

    private func firstView<T: NSView>(of type: T.Type, in view: NSView) -> T? {
        if let match = view as? T { return match }
        for subview in view.subviews {
            if let match = firstView(of: type, in: subview) { return match }
        }
        return nil
    }

    private func allViews<T: NSView>(of type: T.Type, in view: NSView) -> [T] {
        var found: [T] = []
        if let match = view as? T { found.append(match) }
        for subview in view.subviews { found += allViews(of: type, in: subview) }
        return found
    }

    /// Streams `count` files through the live-row path — pipeline_file, then the
    /// timestamp and organize results, then pipeline_result — as the pipeline emits them.
    private func stream(_ count: Int, into state: AppState, fileName: (Int) -> String) {
        for i in 0..<count {
            let file = fileName(i)
            let lines = [
                #"{"event": "pipeline_file", "file": "\#(file)"}"#,
                #"{"event": "timestamp_result", "file": "\#(file)", "action": "would_fix", "original_time": "2025:08:15 14:08:5\#(i % 10)+09:00", "corrected_time": "2025:08:15 14:08:5\#(i % 10)+09:00", "source": "datetimeoriginal", "timezone": "+09:00", "correction_mode": "timezone", "original_epoch": \#(1755000000 + i * 60).0, "corrected_epoch": \#(1755000000 + i * 60).0, "requires_force_timezone": false, "stale_fields": ["Keys:CreationDate", "QuickTime:CreateDate"]}"#,
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
        return try XCTUnwrap(firstView(of: NSTableView.self, in: host), "no NSTableView hosted")
    }

    func testEveryColumnFitsItsContentAfterRowsFillIn() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let hosted = host(state)
        stream(30, into: state) { "VID_20250815_1408\(String(format: "%02d", $0))_00_\(String(format: "%03d", $0)).insv" }
        let table = try table(in: hosted)

        let rows = state.visibleRows
        XCTAssertEqual(rows.count, 30)
        let columns = table.tableColumns
        // Widths must survive further layout passes: SwiftUI's default column
        // autoresizing would squeeze them back to the panel's width.
        RunLoop.main.run(until: Date().addingTimeInterval(0.5))
        table.enclosingScrollView?.layoutSubtreeIfNeeded()
        XCTAssertEqual(columns.count, 7, "file, timeline, original, corrected, timestamp, destination, status")

        let widest: [(index: Int, name: String, width: CGFloat)] = [
            (0, "file", rows.map { width($0.file, mono) }.max()!),
            (2, "original", rows.map { width($0.originalTimeDisplay ?? "", mono) }.max()!),
            (3, "corrected", rows.map { width($0.correctedTime ?? "", mono) }.max()!),
            (4, "timestamp", width(Strings.DiffTable.wouldFixChange, system)),
            (5, "destination", rows.map { width(($0.dest! as NSString).lastPathComponent, mono) }.max()!),
            (6, "status", rows.map { width($0.outcome.statusLabel ?? "", system) }.max()!),
        ]
        for column in widest {
            XCTAssertGreaterThanOrEqual(
                columns[column.index].width, column.width,
                "\(column.name) column (\(columns[column.index].width)pt) must fit its widest text (\(column.width)pt)")
        }

        // The timeline range covers every row's epochs, so every mark lands in the cell.
        let scale = RowMeasurements().timelineScale(for: rows)
        for row in rows {
            for epoch in [row.originalEpoch, row.correctedEpoch].compactMap({ $0 }) {
                let fraction = scale.fraction(for: epoch)
                XCTAssertTrue((0...1).contains(fraction), "epoch \(epoch) lands at \(fraction), outside the timeline")
            }
        }
    }

    /// The app's conditions, not the bare panel's: `ContentView` (which carries
    /// `WindowEdgeGrowthController`) in a window that is on screen, with a run starting
    /// after the panel is open so the window grows while the rows stream in.
    func testEveryColumnFitsItsContentInAVisibleWindowDuringARun() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let host = NSHostingView(rootView: ContentView(state: state))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 800),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.contentView = host
        window.orderFrontRegardless()
        defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))

        state.isRunning = true
        RunLoop.main.run(until: Date().addingTimeInterval(0.1))
        stream(30, into: state) { "VID_20250815_1408\(String(format: "%02d", $0))_00_\(String(format: "%03d", $0)).insv" }
        state.isRunning = false
        RunLoop.main.run(until: Date().addingTimeInterval(1.0))
        // The sidebar's `List` is an `NSTableView` too, and precedes the panel in the
        // window: the Files table is the one with the panel's columns.
        let table = try XCTUnwrap(
            allViews(of: NSTableView.self, in: host).first { $0.tableColumns.count == 7 },
            "no seven-column NSTableView hosted")
        let scrollView = try XCTUnwrap(table.enclosingScrollView)

        let rows = state.visibleRows
        XCTAssertEqual(rows.count, 30)
        let columns = table.tableColumns
        let widest: [(index: Int, name: String, width: CGFloat)] = [
            (0, "file", rows.map { width($0.file, mono) }.max()!),
            (2, "original", rows.map { width($0.originalTimeDisplay ?? "", mono) }.max()!),
            (3, "corrected", rows.map { width($0.correctedTime ?? "", mono) }.max()!),
            (5, "destination", rows.map { width(($0.dest! as NSString).lastPathComponent, mono) }.max()!),
            (6, "status", rows.map { width($0.outcome.statusLabel ?? "", system) }.max()!),
        ]
        for column in widest {
            XCTAssertGreaterThanOrEqual(
                columns[column.index].width, column.width,
                "\(column.name) column (\(columns[column.index].width)pt) must fit its widest text (\(column.width)pt)")
        }
        XCTAssertGreaterThan(table.frame.width, scrollView.contentView.bounds.width,
                             "the content-sized columns must overflow the panel (\(columns.map { $0.width }))")

        // Double-clicking a divider fits its column: the recognizer must be on this
        // table's header, not on whichever table the window happens to list first.
        let headerView = try XCTUnwrap(table.headerView)
        let doubleClick = headerView.gestureRecognizers.compactMap { $0 as? NSClickGestureRecognizer }
            .first { $0.numberOfClicksRequired == 2 }
        XCTAssertNotNil(doubleClick, "the Files table's header must carry the double-click-to-fit recognizer")
    }

    /// The filename is the one column with a cap: a very long name truncates in the
    /// middle rather than pushing the other columns off the panel.
    func testFilenameColumnIsCappedAndOthersAreNot() throws {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        let hosted = host(state)
        let long = String(repeating: "VeryLongCameraFileName_", count: 5) + "0001.insv"
        stream(3, into: state) { _ in long }
        let table = try table(in: hosted)

        XCTAssertGreaterThan(width(long, mono), DiffTableView.fileColumnMaxWidth, "the fixture must exceed the cap")
        XCTAssertLessThanOrEqual(table.tableColumns[0].width, DiffTableView.fileColumnMaxWidth)
        XCTAssertGreaterThanOrEqual(table.tableColumns[5].width, width(long, mono),
                                    "the destination column has no cap and fits the same long name")
    }
}
