import XCTest
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
}
