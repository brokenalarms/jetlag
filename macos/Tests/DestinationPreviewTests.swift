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

    /// The pipeline substitutes the group only when one is given, so the preview
    /// does too.
    func testAFolderTemplateWithoutAGroupKeepsItsPlaceholder() {
        let preview = session(folderTemplate: "{{YYYY-MM-DD}}/{{GROUP}}").destinationPreview

        XCTAssertEqual(preview, "/Volumes/Media/Ready/YYYY-MM-DD/{{GROUP}}")
    }
}
