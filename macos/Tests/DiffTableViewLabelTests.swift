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

    // MARK: - Original column source subtitle / action column writes summary

    /// The Original column's cell must carry the timestamp source (e.g.
    /// "DateTimeOriginal") as its detail line, so the reader can see where the
    /// value was read from without cross-referencing the timestamp/action column.
    func testOriginalColumnDetailShowsTheTimestampSource() {
        var diffRow = row(timestampAction: "would_fix")
        diffRow.timestampSource = .dateTimeOriginal

        let cells = view.cellTexts(diffRow)
        let originalCell = cells[2]

        XCTAssertEqual(originalCell.parts.last?.text, Strings.DiffTable.sourceDateTimeOriginal)
    }

    /// The timestamp/action column's detail line must state what a would-fix
    /// writes, not repeat the source label — a row with identical Original and
    /// Corrected values otherwise gives no reason for the badge it shows.
    func testActionColumnDetailShowsTheWritesSummaryNotTheSource() {
        var diffRow = row(timestampAction: "would_fix")
        diffRow.timestampSource = .dateTimeOriginal
        diffRow.staleFields = ["DateTimeOriginal", "CreateDate"]

        let cells = view.cellTexts(diffRow)
        let actionCell = cells[4]

        XCTAssertEqual(actionCell.parts.last?.text,
                       Strings.DiffTable.wouldWrite("DateTimeOriginal, CreateDate"))
    }

    /// The action and status columns carry the same writes subtitle and must not
    /// stretch to fit every listed field: a fourth field (e.g.
    /// QuickTime:MediaCreateDate) must measure to the same capped width as three
    /// fields, not wider — proving the column truncates rather than grows.
    func testActionAndStatusColumnsCapWidthAtTheWritesSubtitle() {
        var diffRow = row(timestampAction: "would_fix")
        diffRow.staleFields = ["Keys:CreationDate", "QuickTime:CreateDate", "QuickTime:TrackCreateDate"]
        let threeFieldCells = view.cellTexts(diffRow)

        diffRow.staleFields.append("QuickTime:MediaCreateDate")
        let fourFieldCells = view.cellTexts(diffRow)

        for index in [4, 6] {
            XCTAssertEqual(threeFieldCells[index].maxWidth, DiffTableView.writesColumnMaxWidth)
            XCTAssertEqual(DiffTableView.idealWidth(of: threeFieldCells[index]),
                           DiffTableView.writesColumnMaxWidth)
            XCTAssertEqual(DiffTableView.idealWidth(of: fourFieldCells[index]),
                           DiffTableView.writesColumnMaxWidth)
        }
    }
}
