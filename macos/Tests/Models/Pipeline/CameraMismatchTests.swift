import XCTest
@testable import Jetlag

/// Covers the flag on a file whose own camera differs from the profile's. The
/// pipeline leaves the camera's Make/Model in place and reports them on
/// `tag_result`; the row carries them so the table can show the file was likely
/// imported under the wrong profile. A file that matches carries nothing.
final class CameraMismatchTests: XCTestCase {

    private func feed(_ state: AppState, _ lines: [String]) {
        for line in lines {
            state.appendLog(LogLine(text: line, stream: .stdout))
        }
    }

    private func row(after tagResult: String) -> DiffTableRow? {
        let state = AppState()
        feed(state, [
            #"{"event": "pipeline_file", "file": "A7V01670.ARW"}"#,
            tagResult,
            #"{"event": "pipeline_result", "file": "A7V01670.ARW", "result": "would_change"}"#,
        ])
        return state.diffTableRows.first
    }

    /// The camera the file names is what the row reports — the app never
    /// compares against the profile itself, whose settings may have moved on.
    func testMismatchedCameraReachesTheRow() {
        let row = row(after: #"{"event": "tag_result", "file": "A7V01670.ARW", "action": "already_correct", "tags_added": [], "exif_make": "", "exif_model": "", "file_model": "ILCE-7M5"}"#)

        XCTAssertEqual(row?.fileCamera, FileCamera(make: nil, model: "ILCE-7M5"))
        XCTAssertEqual(row?.fileCamera?.name, "ILCE-7M5")
    }

    /// No file_make or file_model means the camera agrees, so nothing is flagged.
    func testMatchingCameraIsNotFlagged() {
        let row = row(after: #"{"event": "tag_result", "file": "A7V01670.ARW", "action": "tagged", "tags_added": ["sony-a7v"], "exif_make": "", "exif_model": ""}"#)

        XCTAssertNotNil(row)
        XCTAssertNil(row?.fileCamera)
    }
}
