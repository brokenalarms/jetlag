import XCTest
import Yams
@testable import Jetlag

/// The Organize step previews where files will land. It has to lay the path out
/// exactly as the pipeline will, so a profile's own `folder_template` — which
/// the preview used to ignore — is what it shows when there is one.
final class DestinationPreviewTests: XCTestCase {

    private func session(folderTemplate: String? = nil, group: String = "") -> WorkflowSession {
        var profile = MediaProfile(type: .video, readyDir: "/Volumes/Media/Ready")
        profile.folderTemplate = folderTemplate
        let session = WorkflowSession(profile: profile, profileName: "cam")
        session.group = group
        return session
    }

    func testDefaultLayoutIsYearThenDate() {
        XCTAssertEqual(session().destinationPreview, "/Volumes/Media/Ready/YYYY/YYYY-MM-DD")
    }

    func testAGroupGoesBetweenYearAndDate() {
        XCTAssertEqual(session(group: "Japan").destinationPreview,
                       "/Volumes/Media/Ready/YYYY/Japan/YYYY-MM-DD")
    }

    func testTheProfilesFolderTemplateIsWhatIsShown() {
        let preview = session(folderTemplate: "{{YYYY}}/{{MMM}}/{{GROUP}}", group: "Japan").destinationPreview

        XCTAssertEqual(preview, "/Volumes/Media/Ready/YYYY/MMM/Japan")
    }

    /// The group is an optional grouping folder: without one the pipeline leaves
    /// that folder out, so the preview does too.
    func testAFolderTemplateWithoutAGroupLeavesTheGroupFolderOut() {
        let preview = session(folderTemplate: "{{YYYY}}/{{GROUP}}/{{YYYY-MM-DD}}").destinationPreview

        XCTAssertEqual(preview, "/Volumes/Media/Ready/YYYY/YYYY-MM-DD")
    }

    /// scripts/tests/commands/folder-template-cases.yaml, the cases the scripts'
    /// expand_path_template is also held to. The preview shows date parts as
    /// placeholders, so they are filled with the cases' date (2025-08-15) before
    /// comparing.
    private static let casesURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Workflow
        .deletingLastPathComponent()   // Models
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .deletingLastPathComponent()   // repo root
        .appendingPathComponent("scripts/tests/commands/folder-template-cases.yaml")

    func testThePreviewLaysOutEverySharedCaseAsTheScriptsDo() throws {
        let text = try String(contentsOf: Self.casesURL, encoding: .utf8)
        let root = try Yams.load(yaml: text) as? [String: Any]
        let cases = try XCTUnwrap(root?["cases"] as? [[String: Any]], "no cases in \(Self.casesURL.path)")
        XCTAssertFalse(cases.isEmpty)
        let readyDir = "/Volumes/Media/Ready/"
        for testCase in cases {
            let template = testCase["template"] as? String
            let group = testCase["group"] as? String ?? ""
            let expected = try XCTUnwrap(testCase["expected"] as? String)
            let preview = session(folderTemplate: template, group: group).destinationPreview
            XCTAssertTrue(preview.hasPrefix(readyDir), preview)
            var relative = String(preview.dropFirst(readyDir.count))
            for (placeholder, value) in [("YYYY", "2025"), ("MMM", "Aug"), ("MM", "08"), ("DD", "15")] {
                relative = relative.replacingOccurrences(of: placeholder, with: value)
            }
            XCTAssertEqual(relative, expected, "template \(template ?? "none"), group \"\(group)\"")
        }
    }
}
