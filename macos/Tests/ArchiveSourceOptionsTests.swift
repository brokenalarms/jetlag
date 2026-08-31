import XCTest
@testable import Jetlag

/// The Archive Source step is a destination plus a folder name, mirroring
/// Organize: the default is today's in-place dated rename, a browsed
/// destination moves the folder, and an archive that resolves back to the
/// source path moves and renames nothing — so it must block the run rather
/// than silently doing nothing.
final class ArchiveSourceOptionsTests: XCTestCase {

    private var tempDirs: [String] = []

    override func tearDown() {
        super.tearDown()
        for dir in tempDirs {
            try? FileManager.default.removeItem(atPath: dir)
        }
        tempDirs = []
    }

    private func makeTempDir(named name: String? = nil) -> String {
        let parent = NSTemporaryDirectory() + UUID().uuidString
        let path = name.map { parent + "/" + $0 } ?? parent
        try! FileManager.default.createDirectory(atPath: path, withIntermediateDirectories: true)
        tempDirs.append(parent)
        return path
    }

    /// A session whose source and ready dirs really exist, with every step on:
    /// readiness questions are then only about the archive settings.
    private func makeSession(sourceName: String = "DCIM") -> WorkflowSession {
        let source = makeTempDir(named: sourceName)
        let profile = MediaProfile(
            type: .video,
            sourceDir: source,
            readyDir: makeTempDir(),
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(profile: profile, profileName: "test-profile")
        session.enabledSteps = Set(session.availableSteps)
        session.timezone.value = "Asia/Tokyo"
        return session
    }

    private func today() -> String {
        WorkflowSession.archivedNameDate(Date())
    }

    func testDefaultsToAnInPlaceDatedRename() {
        let session = makeSession()
        let sourceParent = (session.sourceDir.current as NSString).deletingLastPathComponent

        XCTAssertEqual(session.archiveDestination, sourceParent,
            "destination defaults to where the source folder already is")
        XCTAssertTrue(session.renameSourceDir, "rename is on by default")
        XCTAssertEqual(session.archivedName, "DCIM - copied \(today())")
        XCTAssertNil(session.validateArchiveSource())
        XCTAssertTrue(session.isStepReady(.archiveSource))
    }

    func testRenameOffShowsTheOriginalFolderName() {
        let session = makeSession()
        session.renameSourceDir = false

        XCTAssertEqual(session.archivedName, "DCIM",
            "with rename off the field shows the folder's own name")
    }

    func testRenameOffWithUnchangedDestinationBlocksTheRun() {
        let session = makeSession()
        session.renameSourceDir = false

        XCTAssertEqual(session.validateArchiveSource(), Strings.Workflow.archiveNoChange,
            "archiving the source onto itself is a no-op and must be reported")
        XCTAssertFalse(session.isStepReady(.archiveSource))
        XCTAssertFalse(session.allStepsReady, "Dry Run / Apply / Run are blocked")
    }

    func testRenameOffWithBrowsedDestinationIsValid() {
        let session = makeSession()
        session.renameSourceDir = false
        session.archiveDestination = makeTempDir()

        XCTAssertNil(session.validateArchiveSource(),
            "moving the folder without renaming it still archives it")
        XCTAssertTrue(session.allStepsReady)

        let (_, args) = session.buildPipelineArgs()
        XCTAssertEqual(args[args.firstIndex(of: "--archive-destination")! + 1],
                       session.archiveDestination)
        XCTAssertEqual(args[args.firstIndex(of: "--archived-name")! + 1], "DCIM")
    }

    func testTypingTheOriginalNameBackIsAlsoANoOp() {
        let session = makeSession()
        session.archivedName = "DCIM"

        XCTAssertEqual(session.validateArchiveSource(), Strings.Workflow.archiveNoChange)
    }

    func testMissingDestinationDirectoryBlocksTheRun() {
        let session = makeSession()
        session.archiveDestination = "/nonexistent/archive/target"

        XCTAssertEqual(session.validateArchiveSource(), Strings.Errors.directoryNotFound)
        XCTAssertFalse(session.allStepsReady)
    }

    func testArchiveSettingsAreIgnoredWhileTheStepIsOff() {
        let session = makeSession()
        session.renameSourceDir = false
        session.enabledSteps.remove(.archiveSource)

        XCTAssertNil(session.validateArchiveSource())
        XCTAssertTrue(session.allStepsReady)

        let (_, args) = session.buildPipelineArgs()
        XCTAssertFalse(args.contains("--archive-destination"))
        XCTAssertFalse(args.contains("--archived-name"))
    }

    func testCustomNameAndDestinationAreCarriedIntoTheRun() {
        let session = makeSession()
        let elsewhere = makeTempDir()
        session.archiveDestination = elsewhere
        session.archivedName = "Japan trip"

        let (_, args) = session.buildPipelineArgs()
        XCTAssertEqual(args[args.firstIndex(of: "--archive-destination")! + 1], elsewhere)
        XCTAssertEqual(args[args.firstIndex(of: "--archived-name")! + 1], "Japan trip")
        XCTAssertNil(session.validateArchiveSource())
    }

    func testRecheckingRenameRestoresTheEditedName() {
        let session = makeSession()
        session.archivedName = "Japan trip"
        session.renameSourceDir = false

        XCTAssertEqual(session.archivedName, "DCIM")

        session.renameSourceDir = true
        XCTAssertEqual(session.archivedName, "Japan trip",
            "unchecking must not discard the name the user typed")
    }
}
