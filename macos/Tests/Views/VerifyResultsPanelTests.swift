import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The Verify tab shows its results in the same panel and table as Workflow. These host
/// `VerifyResultsPanel` over a session at each point of a check and read what it shows
/// through the accessibility tree, and host `VerifyTableView` to read the columns it
/// declares: a location missing from the table, or a check that reads as idle, would
/// let a card be wiped that is not on every backup.
final class VerifyResultsPanelTests: XCTestCase {

    override func setUp() {
        AccessibilityTree.setBuilt(true)
    }

    override func tearDown() {
        AccessibilityTree.setBuilt(false)
    }

    private func host<V: View>(_ view: V) -> NSHostingView<V> {
        let host = NSHostingView(rootView: view)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 500),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 900, height: 500)
        HostedWindow.settle(host)
        HostedWindow.settle(host)
        return host
    }

    private func texts(in view: NSView) -> [String] {
        AccessibilityTree.nodes(in: view)
            .filter { $0.accessibilityRole?() == .staticText }
            .compactMap { node in
                let value: Any?? = node.accessibilityValue?()
                return (value ?? nil) as? String
            }
    }

    private func findTable(in view: NSView) -> NSTableView? {
        if let table = view as? NSTableView { return table }
        for subview in view.subviews {
            if let found = findTable(in: subview) { return found }
        }
        return nil
    }

    private func report(_ lines: [String]) throws -> VerifyReport {
        var report = VerifyReport()
        for line in lines {
            report.apply(try XCTUnwrap(VerifyEvent.decode(line)))
        }
        return report
    }

    private static let location = #"{"event":"verify_location","location":"T9","root":"/Volumes/T9","remote":false,"network":false,"reachable":true,"files":1}"#
    private static let matchedFile = [
        #"{"event":"verify_file","file":"DCIM/a.mp4","kind":"media","size":10}"#,
        #"{"event":"verify_result","file":"DCIM/a.mp4","location":"T9","verdict":"matched","basis":"size","copies":["a.mp4"]}"#,
    ]
    private static let missingFile = [
        #"{"event":"verify_file","file":"DCIM/b.mp4","kind":"media","size":10}"#,
        #"{"event":"verify_result","file":"DCIM/b.mp4","location":"T9","verdict":"missing","copies":[]}"#,
    ]

    private func summary(checked: Int, attention: Int) -> String {
        #"{"event":"verify_summary","checked":\#(checked),"on_every_location":\#(checked - attention),"need_attention":\#(attention),"not_checked":0,"not_checked_kinds":[]}"#
    }

    private func summaryLine(_ report: VerifyReport) throws -> String {
        let summary = try XCTUnwrap(report.summary)
        return Strings.Verify.summary(checked: summary.checked, onEvery: summary.onEveryLocation,
                                      attention: summary.needAttention, notChecked: summary.notChecked,
                                      kinds: summary.notCheckedKinds)
    }

    /// A check runs through the panel's phases in order: the prompt before any check,
    /// the spinner until the first file arrives, then the table under a header that
    /// carries the summary, so a short table reads as the files needing attention.
    func testPanelFollowsTheCheckFromIdleToResults() throws {
        let state = AppState()
        XCTAssertEqual(texts(in: host(VerifyResultsPanel(state: state))), [Strings.Verify.idleLabel])

        state.verifySession.isRunning = true
        XCTAssertEqual(texts(in: host(VerifyResultsPanel(state: state))), [Strings.Verify.checkingLabel])

        state.verifySession.report = try report([Self.location] + Self.matchedFile + Self.missingFile
                                                 + [summary(checked: 2, attention: 1)])
        state.verifySession.isRunning = false
        let results = host(VerifyResultsPanel(state: state))
        XCTAssertEqual(texts(in: results), [Strings.Verify.resultsTitle, try summaryLine(state.verifySession.report)])
        let table = try XCTUnwrap(findTable(in: results))
        XCTAssertEqual(table.numberOfRows, 1, "a matched file is hidden while Show matched is off")

        state.verifySession.showMatched = true
        XCTAssertEqual(try XCTUnwrap(findTable(in: host(VerifyResultsPanel(state: state)))).numberOfRows, 2)
    }

    /// Every file on every location leaves no row to show: the panel says so, with the
    /// summary, rather than showing an empty table that reads as a check that found nothing.
    func testNothingNeedingAttentionShowsTheAllClearMessage() throws {
        let state = AppState()
        state.verifySession.report = try report([Self.location] + Self.matchedFile + [summary(checked: 1, attention: 0)])
        XCTAssertEqual(Set(texts(in: host(VerifyResultsPanel(state: state)))),
                       [Strings.Verify.allClear, try summaryLine(state.verifySession.report)])
    }

    /// The table carries the file, one status column per location the check reported, in
    /// the order reported, then the details.
    func testTableHasAColumnPerLocation() throws {
        let rows = try report([Self.location] + Self.missingFile).rows
        let table = try XCTUnwrap(findTable(in: host(
            VerifyTableView(rows: rows, locations: ["T9", "NAS", "Cloud"], source: "/Volumes/CARD"))))
        XCTAssertEqual(table.tableColumns.map(\.title),
                       [Strings.Verify.fileColumn, "T9", "NAS", "Cloud", Strings.Verify.detailsColumn])
    }

    /// The shared table draws at most ten columns, and draws nothing past that, so the
    /// locations stop at the cap rather than the whole table disappearing.
    func testLocationColumnsStopAtTheTablesCap() throws {
        let rows = try report([Self.location] + Self.missingFile).rows
        let locations = (1...12).map { "L\($0)" }
        let table = try XCTUnwrap(findTable(in: host(
            VerifyTableView(rows: rows, locations: locations, source: "/Volumes/CARD"))))
        XCTAssertEqual(table.tableColumns.map(\.title),
                       [Strings.Verify.fileColumn] + locations.prefix(VerifyTableView.maxLocationColumns)
                       + [Strings.Verify.detailsColumn])
    }

    /// Only a match reads as done; a location that could not be reached reads as not
    /// checked, a file that could not be compared as a warning, and every way a copy is
    /// absent or differs as a failure.
    func testEveryVerdictHasItsBadge() {
        let expected: [VerifyVerdict: StatusBadgeState] = [
            .matched: .done,
            .unverifiable: .custom(icon: "questionmark.circle.fill", tint: Theme.Status.warning),
            .unreachable: .unchanged,
            .missing: .failed,
            .duplicate: .failed,
            .dataDiffers: .failed,
            .sizeDiffers: .failed,
            .hashMismatch: .failed,
        ]
        XCTAssertEqual(Set(expected.keys), Set(VerifyVerdict.allCases))
        for verdict in VerifyVerdict.allCases {
            XCTAssertEqual(VerifyTableView.badgeState(verdict), expected[verdict], "\(verdict)")
        }
    }
}
