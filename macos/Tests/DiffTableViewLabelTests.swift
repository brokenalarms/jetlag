import XCTest
@testable import Jetlag

/// `DiffTableView.changeBadgeText` builds the timestamp badge from
/// `RowOutcome.Correction`, decoded from `row.timestampAction`, not from the raw
/// string — one case per `Correction` proves the label for every decoded token,
/// so a case the switch stops handling shows up here instead of silently falling
/// through a `default`.
final class DiffTableViewLabelTests: XCTestCase {

    private let view = DiffTableView(rows: [])

    private func row(timestampAction: String?, correctionMode: String? = nil,
                     timeOffsetDisplay: String? = nil, timestampError: String? = nil) -> DiffTableRow {
        var row = DiffTableRow(file: "DJI_0001.MP4")
        row.timestampAction = timestampAction
        row.correctionMode = correctionMode
        row.timeOffsetDisplay = timeOffsetDisplay
        row.timestampError = timestampError
        return row
    }

    func testFixedCorrectionShowsFixedBadge() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: "fixed")),
                       Strings.DiffTable.fixedChange)
    }

    func testWouldFixCorrectionShowsWouldFixBadge() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: "would_fix")),
                       Strings.DiffTable.wouldFixChange)
    }

    func testWouldFixCorrectionInTimeModeShowsTheOffsetInstead() {
        let text = view.changeBadgeText(row(timestampAction: "would_fix",
                                            correctionMode: "time",
                                            timeOffsetDisplay: "+09:00"))

        XCTAssertEqual(text, "+09:00")
    }

    func testNoChangeCorrectionShowsNoChangeBadge() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: "no_change")),
                       Strings.DiffTable.noChangeChange)
    }

    func testErrorCorrectionShowsTheErrorMessage() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: "error",
                                                timestampError: "camera clock drift")),
                       "camera clock drift")
    }

    func testErrorCorrectionWithoutAMessageFallsBackToTheGenericLabel() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: "error")),
                       Strings.DiffTable.errorChange)
    }

    func testUnreportedCorrectionShowsAnEmDash() {
        XCTAssertEqual(view.changeBadgeText(row(timestampAction: nil)), "—")
    }
}
