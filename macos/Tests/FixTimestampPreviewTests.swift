import XCTest
@testable import Jetlag

/// The Fix Timestamps step's hint must never claim more (or less) than what the
/// pipeline will actually do. In 'From filenames' mode the declared zone still
/// applies — it labels the naive digits read from the filename — so the hint
/// must name it exactly as the metadata branch does, not omit it.
final class FixTimestampPreviewTests: XCTestCase {

    private func state(inferFromFilenames: Bool, timezone: String?) -> AppState {
        let state = AppState()
        state.workflowSession.enabledSteps.insert(.fixTimestamps)
        state.workflowSession.inferFromFilenames = inferFromFilenames
        state.workflowSession.timezone.value = timezone ?? ""
        return state
    }

    /// AC 1: 'From filenames' names the declared zone's city and offset.
    func testFilenameModeNamesTheDeclaredZone() {
        let view = WorkflowView(state: state(inferFromFilenames: true, timezone: "Asia/Seoul"))

        guard let preview = view.fixTimestampPreview else {
            return XCTFail("expected a preview")
        }
        XCTAssertTrue(preview.contains("Seoul"), preview)
        XCTAssertTrue(preview.contains("+0900"), preview)
    }

    /// AC 2: metadata mode's wording is unchanged.
    func testMetadataModeAppliesTheDeclaredZone() {
        let view = WorkflowView(state: state(inferFromFilenames: false, timezone: "Asia/Seoul"))

        XCTAssertEqual(view.fixTimestampPreview, "Apply Seoul time (+0900)")
    }

    /// AC 1 (multi-offset zones): filename mode mirrors the metadata branch's
    /// "resolved per file" wording when the zone observes daylight saving.
    func testFilenameModeWithMultiOffsetZoneIsResolvedPerFile() throws {
        guard let option = TimezoneCatalog.option("America/New_York"), option.offsets.count > 1 else {
            throw XCTSkip("host machine's tzdata does not report America/New_York as a DST zone")
        }
        let view = WorkflowView(state: state(inferFromFilenames: true, timezone: "America/New_York"))

        guard let preview = view.fixTimestampPreview else {
            return XCTFail("expected a preview")
        }
        XCTAssertTrue(preview.contains("New York"), preview)
        XCTAssertTrue(preview.contains("resolved per file"), preview)
    }

    /// AC 4: with no zone declared, neither mode claims one.
    func testNoZoneSelectedClaimsNoZoneInEitherMode() {
        let filenamePreview = WorkflowView(state: state(inferFromFilenames: true, timezone: nil)).fixTimestampPreview
        let metadataPreview = WorkflowView(state: state(inferFromFilenames: false, timezone: nil)).fixTimestampPreview

        XCTAssertEqual(filenamePreview, "Use filename dates as timestamp source")
        XCTAssertNil(metadataPreview)
    }
}
