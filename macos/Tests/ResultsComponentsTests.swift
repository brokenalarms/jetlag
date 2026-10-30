import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The results components take plain data so a screen other than the pipeline's Files
/// panel can use them. These host `ResultsTable` over a row type that is not
/// `DiffTableRow`, with its own columns, and check what the table actually does.
final class ResultsComponentsTests: XCTestCase {

    private struct BackupRow: Identifiable {
        let id: String
        let path: String
        let backups: [String]
    }

    private let mono = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)

    private func columns(backupCount: Int) -> [ResultsColumn<BackupRow>] {
        let mono = self.mono
        var columns = [
            ResultsColumn<BackupRow>("File", minWidth: 80,
                                     measure: { CellText([($0.path, mono)]) },
                                     cell: { Text($0.path) }),
        ]
        for index in 0..<backupCount {
            columns.append(ResultsColumn("Backup \(index + 1)", minWidth: 60,
                                         measure: { CellText([($0.backups[index], mono)]) },
                                         cell: { Text($0.backups[index]) }))
        }
        return columns
    }

    private func resultsTable(rows: [BackupRow], backupCount: Int,
                              measurements: ColumnMeasurements) -> some View {
        ResultsTable(rows: rows, columns: columns(backupCount: backupCount),
                     measurements: measurements, fileURL: { URL(fileURLWithPath: $0.path) })
            .frame(width: 700, height: 300)
    }

    /// Rows arrive one at a time in a run, which is also what gives the auto-sizer an
    /// update in which the lazily created table exists: the last row is appended after the
    /// table has been laid out once.
    private func hostedTable(rows: [BackupRow], backupCount: Int) -> NSTableView? {
        let measurements = ColumnMeasurements()
        let host = NSHostingView(rootView: resultsTable(rows: Array(rows.dropLast()), backupCount: backupCount,
                                                        measurements: measurements))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 300),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 700, height: 300)
        func settle() {
            for _ in 0..<5 {
                host.layoutSubtreeIfNeeded()
                RunLoop.main.run(until: Date().addingTimeInterval(0.1))
            }
        }
        settle()
        host.rootView = resultsTable(rows: rows, backupCount: backupCount, measurements: measurements)
        settle()
        return findTable(in: host)
    }

    private func findTable(in view: NSView) -> NSTableView? {
        if let table = view as? NSTableView { return table }
        for subview in view.subviews {
            if let found = findTable(in: subview) { return found }
        }
        return nil
    }

    /// A Verify screen declares one status column per backup location; the table draws
    /// exactly the columns it was given, titled as given.
    func testTableDrawsOneColumnPerDefinition() throws {
        let rows = [BackupRow(id: "a", path: "/tmp/a.mp4", backups: ["ok", "missing", "ok"])]
        let table = try XCTUnwrap(hostedTable(rows: rows, backupCount: 3))
        XCTAssertEqual(table.tableColumns.map(\.title), ["File", "Backup 1", "Backup 2", "Backup 3"])
    }

    /// Column auto-sizing works from the caller's own measurements: a column grows to the
    /// widest text its rows put in it.
    func testColumnsFitTheirWidestCell() throws {
        let long = String(repeating: "m", count: 60)
        let rows = [BackupRow(id: "a", path: "/tmp/a.mp4", backups: ["ok"]),
                    BackupRow(id: "b", path: "/tmp/b.mp4", backups: [long])]
        let table = try XCTUnwrap(hostedTable(rows: rows, backupCount: 1))
        let widest = (long as NSString).size(withAttributes: [.font: mono]).width
        XCTAssertGreaterThanOrEqual(table.tableColumns[1].width, widest)
    }

    /// Show in Finder and Quick Look act on the files of the selected rows only.
    func testFileURLsResolveOnlyTheSelectedRows() {
        let rows = [BackupRow(id: "a", path: "/tmp/a.mp4", backups: []),
                    BackupRow(id: "b", path: "/tmp/b.mp4", backups: [])]
        let urls = ResultsTable<BackupRow>.fileURLs(for: ["b"], in: rows,
                                                    locating: { URL(fileURLWithPath: $0.path) })
        XCTAssertEqual(urls.map(\.path), ["/tmp/b.mp4"])
    }

    private func statusBadge(_ row: DiffTableRow) -> (state: StatusBadgeState, label: String) {
        let view = DiffTableView(rows: [row])
        return (view.statusState(row), view.statusText(row))
    }

    /// A row the pipeline has not finished spins with the last stage it completed, and
    /// before any stage completes it has no label at all: the badge draws text only when
    /// the label is non-empty.
    func testPendingRowShowsItsLastCompletedStage() {
        var row = DiffTableRow(file: "a.mp4")
        XCTAssertEqual(statusBadge(row).state, .pending)
        XCTAssertEqual(statusBadge(row).label, "")

        row.markStageComplete("ingest")
        row.markStageComplete("fix-timestamp")
        XCTAssertEqual(statusBadge(row).state, .pending)
        XCTAssertEqual(statusBadge(row).label, row.lastCompletedStageLabel)
    }

    /// A finished row with nothing to do and a failed row read as their fixed strings,
    /// whatever the action tokens say.
    func testUnchangedAndFailedRowsUseTheirFixedStrings() {
        var unchanged = DiffTableRow(file: "a.mp4")
        unchanged.pipelineResult = "unchanged"
        unchanged.timestampAction = "fixed"
        XCTAssertEqual(statusBadge(unchanged).state, .unchanged)
        XCTAssertEqual(statusBadge(unchanged).label, Strings.DiffTable.noChangeStatus)

        var failed = DiffTableRow(file: "a.mp4")
        failed.pipelineResult = "failed"
        failed.timestampAction = "fixed"
        XCTAssertEqual(statusBadge(failed).state, .failed)
        XCTAssertEqual(statusBadge(failed).label, Strings.DiffTable.failedStatus)
    }

    /// A result the table has no state for is shown as the pipeline reported it, with
    /// no icon; `in_progress` is the one the app itself assigns mid-run.
    func testUnknownResultIsShownAsReported() {
        var row = DiffTableRow(file: "a.mp4")
        row.pipelineResult = "in_progress"
        XCTAssertEqual(statusBadge(row).state, .plain)
        XCTAssertEqual(statusBadge(row).label, "in_progress")
    }

    /// Changed and would-change rows are composed from the outcome's action tokens,
    /// falling back to the generic status when the tokens contribute nothing.
    func testChangedRowsComposeTheirLabelFromTheOutcome() {
        var fixed = DiffTableRow(file: "a.mp4")
        fixed.pipelineResult = "changed"
        fixed.timestampAction = "fixed"
        XCTAssertEqual(statusBadge(fixed).state, .done)
        XCTAssertEqual(statusBadge(fixed).label, fixed.outcome.statusLabel)

        var changed = DiffTableRow(file: "a.mp4")
        changed.pipelineResult = "changed"
        XCTAssertEqual(statusBadge(changed).state, .done)
        XCTAssertEqual(statusBadge(changed).label, Strings.DiffTable.changedStatus)

        var wouldFix = DiffTableRow(file: "a.mp4")
        wouldFix.pipelineResult = "would_change"
        wouldFix.timestampAction = "would_fix"
        XCTAssertEqual(statusBadge(wouldFix).state, .wouldDo)
        XCTAssertEqual(statusBadge(wouldFix).label, wouldFix.outcome.statusLabel)

        var wouldChange = DiffTableRow(file: "a.mp4")
        wouldChange.pipelineResult = "would_change"
        XCTAssertEqual(statusBadge(wouldChange).state, .wouldDo)
        XCTAssertEqual(statusBadge(wouldChange).label, Strings.DiffTable.wouldChangeStatus)
    }
}

/// The panel and badge take plain data, so these host each on its own, with no AppState
/// or pipeline, and read what it exposes through the accessibility tree.
final class ResultsPanelTests: XCTestCase {

    override func setUp() {
        AccessibilityTree.setBuilt(true)
    }

    override func tearDown() {
        AccessibilityTree.setBuilt(false)
    }

    private func host<V: View>(_ view: V) -> NSHostingView<V> {
        let host = NSHostingView(rootView: view)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 400),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 600, height: 400)
        HostedWindow.settle(host)
        return host
    }

    private func nodes(_ role: NSAccessibility.Role, in view: NSView) -> [AnyObject] {
        AccessibilityTree.nodes(in: view).filter { $0.accessibilityRole?() == role }
    }

    private func texts(in view: NSView) -> [String] {
        nodes(.staticText, in: view).compactMap { node in
            let value: Any?? = node.accessibilityValue?()
            return (value ?? nil) as? String
        }
    }

    private func logToggle(in view: NSView) -> AnyObject? {
        nodes(.button, in: view).first {
            [Strings.Workflow.showLogOutputHelp, Strings.Workflow.hideLogOutputHelp]
                .contains($0.accessibilityHelp?() ?? "")
        }
    }

    private func panel(_ phase: ResultsPhase, showsLog: Binding<Bool> = .constant(false)) -> some View {
        ResultsPanel(phase: phase, showsLog: showsLog,
                     logLines: [LogLine(text: "log line", stream: .stdout)],
                     logHolder: LogViewHolder(), onClearLog: {}) {
            Text("Panel content")
        }
    }

    /// With results to show, the header states what they are and how many, above the
    /// caller's content.
    func testContentPhaseShowsHeaderAndContent() {
        let phase = ResultsPhase.content(ResultsHeader(icon: "tablecells", title: "Backups", count: "3 files"))
        XCTAssertEqual(texts(in: host(panel(phase))), ["Backups", "3 files", "Panel content"])
    }

    /// The count is optional: a header without one is the title alone.
    func testHeaderWithoutACountShowsOnlyItsTitle() {
        let phase = ResultsPhase.content(ResultsHeader(icon: "tablecells", title: "Backups", count: nil))
        XCTAssertEqual(texts(in: host(panel(phase))), ["Backups", "Panel content"])
    }

    /// Before the first result arrives the panel shows a spinner with the latest progress
    /// line, so a slow scan does not read as a hang. The caller's content is not built.
    func testStartingUpShowsProgressAndItsLatestStatus() {
        let hosted = host(panel(.startingUp(label: "Starting", status: "Scanning card")))
        XCTAssertEqual(texts(in: hosted), ["Starting", "Scanning card"])
        XCTAssertFalse(nodes(.busyIndicator, in: hosted).isEmpty)
    }

    /// No progress line has arrived yet: the label stands alone.
    func testStartingUpWithoutAStatusShowsOnlyItsLabel() {
        XCTAssertEqual(texts(in: host(panel(.startingUp(label: "Starting", status: nil)))), ["Starting"])
    }

    /// A run that found nothing states why, with the thing it is about.
    func testMessagePhaseShowsTitleAndDetail() {
        let hosted = host(panel(.message(title: "No media", detail: "/Volumes/CARD")))
        XCTAssertEqual(Set(texts(in: hosted)), ["No media", "/Volumes/CARD"])
    }

    /// The idle label fills the empty panel, and gives way to the log when it is open.
    func testIdleLabelGivesWayToTheOpenLog() {
        XCTAssertEqual(texts(in: host(panel(.idle(label: "Nothing yet")))), ["Nothing yet"])

        let open = host(panel(.idle(label: "Nothing yet"), showsLog: .constant(true)))
        XCTAssertFalse(texts(in: open).contains("Nothing yet"))
        XCTAssertNotNil(HostedWindow.logScrollView(in: open))
    }

    /// The open log shares the panel evenly with what is above it, and the header belongs
    /// to that share. Laid out on its own, the header's height comes off the top first and
    /// the log sits lower than it does beneath a placeholder of the same flexible height.
    func testHeaderCountsTowardsTheContentsShareOfTheOpenLog() throws {
        func logFrame(_ phase: ResultsPhase) throws -> NSRect {
            let log = try XCTUnwrap(HostedWindow.logScrollView(in: host(panel(phase, showsLog: .constant(true)))))
            return log.convert(log.bounds, to: nil)
        }
        let header = ResultsHeader(icon: "tablecells", title: "Backups", count: nil)
        XCTAssertEqual(try logFrame(.content(header)), try logFrame(.startingUp(label: "Starting", status: nil)))
    }

    /// The bottom bar's toggle opens the log from every phase, closes it again, and its
    /// tooltip says which it will do next.
    func testTerminalToggleOpensAndClosesTheLogInEveryPhase() throws {
        let header = ResultsHeader(icon: "tablecells", title: "Backups", count: nil)
        let phases: [ResultsPhase] = [.content(header), .startingUp(label: "Starting", status: nil),
                                      .message(title: "No media", detail: "/"), .idle(label: "Nothing yet")]
        for phase in phases {
            var showsLog = false
            let binding = Binding(get: { showsLog }, set: { showsLog = $0 })

            let closed = host(panel(phase, showsLog: binding))
            XCTAssertNil(HostedWindow.logScrollView(in: closed))
            let open = try XCTUnwrap(logToggle(in: closed))
            XCTAssertEqual(open.accessibilityHelp?(), Strings.Workflow.showLogOutputHelp)
            XCTAssertEqual(open.accessibilityPerformPress?(), true)
            XCTAssertTrue(showsLog)

            let opened = host(panel(phase, showsLog: binding))
            XCTAssertNotNil(HostedWindow.logScrollView(in: opened))
            let close = try XCTUnwrap(logToggle(in: opened))
            XCTAssertEqual(close.accessibilityHelp?(), Strings.Workflow.hideLogOutputHelp)
            XCTAssertEqual(close.accessibilityPerformPress?(), true)
            XCTAssertFalse(showsLog)
        }
    }

    /// Every state with an icon carries its label beside the icon, including one a caller
    /// defines, such as a Verify screen's "missing". The icon has no accessibility node of
    /// its own, so its presence is measured: the badge is wider than a plain badge, which
    /// is the same label alone.
    func testBadgeStatesShowTheirIconBesideTheirLabel() {
        let plain = host(StatusBadge(state: .plain, label: "Label"))
        XCTAssertEqual(texts(in: plain), ["Label"])
        let states: [StatusBadgeState] = [.done, .wouldDo, .unchanged, .failed,
                                          .custom(icon: "questionmark.folder", tint: .orange)]
        for state in states {
            let hosted = host(StatusBadge(state: state, label: "Label"))
            XCTAssertEqual(texts(in: hosted), ["Label"], "\(state)")
            XCTAssertGreaterThanOrEqual(hosted.fittingSize.width,
                                        plain.fittingSize.width + NSFont.smallSystemFontSize, "\(state)")
            XCTAssertTrue(nodes(.busyIndicator, in: hosted).isEmpty, "\(state)")
        }
    }

    /// A pending badge spins beside the stage it last completed, and with no stage yet it
    /// is the spinner alone, not a spinner beside a blank label.
    func testPendingBadgeSpinsWithItsStageLabel() {
        let staged = host(StatusBadge(state: .pending, label: "Timestamps"))
        XCTAssertFalse(nodes(.busyIndicator, in: staged).isEmpty)
        XCTAssertEqual(texts(in: staged), ["Timestamps"])

        let unstaged = host(StatusBadge(state: .pending, label: ""))
        XCTAssertFalse(nodes(.busyIndicator, in: unstaged).isEmpty)
        XCTAssertEqual(texts(in: unstaged), [])
    }
}
