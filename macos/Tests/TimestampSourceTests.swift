import XCTest
@testable import Jetlag

/// A diff-table row has to be able to explain itself. Two of the facts it needs —
/// which field the correction read, and whether that field's digits are UTC — live
/// only in the pipeline's `source` token, never in the timestamp strings. These
/// tests cover the type that owns that token: its display label, and the Original
/// cell's rendering, which is decided by the source's semantics rather than by
/// inspecting the value.
final class TimestampSourceTests: XCTestCase {

    /// Every token the pipeline emits maps to a label a user can read, so the
    /// Timestamp column can always name the winning source.
    func testEveryEmittedTokenHasALabel() {
        let tokens = ["datetimeoriginal", "creationdate", "mediacreatedate",
                      "filename", "file_birth", "file_mtime"]

        for token in tokens {
            let source = TimestampSource(token: token)
            XCTAssertNotNil(source, "no case for token \(token)")
            XCTAssertFalse(source?.label.isEmpty ?? true, "empty label for \(token)")
        }
    }

    /// A token the app does not know is not guessed at — the row simply shows no
    /// source rather than a wrong one.
    func testUnknownTokenHasNoSource() {
        XCTAssertNil(TimestampSource(token: "something_new"))
        XCTAssertNil(TimestampSource(token: nil))
    }

    /// The QuickTime clock stores a UTC instant, so its original reads as UTC —
    /// the word, not a trailing Z a reader has to decode.
    func testUTCSourceOriginalIsLabelledUTC() {
        let display = TimestampSource.mediaCreateDate
            .originalDisplay("2025:08:30 09:00:00Z")

        XCTAssertEqual(display, "2025:08:30 09:00:00 UTC")
    }

    /// A zoned source already states its own offset, which is passed through:
    /// relabelling it UTC would be a lie about where the footage was shot.
    func testZonedSourceKeepsItsOffset() {
        let display = TimestampSource.dateTimeOriginal
            .originalDisplay("2025:08:15 14:08:51+09:00")

        XCTAssertEqual(display, "2025:08:15 14:08:51+09:00")
    }

    /// A filename carries wall-clock digits and no zone at all, so nothing is added.
    func testNaiveSourceShowsBareDigits() {
        let display = TimestampSource.filename.originalDisplay("2025:08:30 09:00:00")

        XCTAssertEqual(display, "2025:08:30 09:00:00")
    }

    /// The UTC decision comes from the source, not the string: a UTC source whose
    /// value arrived without the zero offset still reads as UTC, and a naive source
    /// is never promoted to UTC by its digits.
    func testUTCIsDecidedByTheSourceNotTheString() {
        XCTAssertEqual(
            TimestampSource.mediaCreateDate.originalDisplay("2025:08:30 09:00:00"),
            "2025:08:30 09:00:00 UTC")
        XCTAssertTrue(TimestampSource.mediaCreateDate.isUTC)
        XCTAssertFalse(TimestampSource.dateTimeOriginal.isUTC)
        XCTAssertFalse(TimestampSource.filename.isUTC)
    }
}
