import XCTest
@testable import Jetlag

final class PipelineArgsTests: XCTestCase {

    private var tempDirs: [String] = []

    override func tearDown() {
        super.tearDown()
        for dir in tempDirs {
            try? FileManager.default.removeItem(atPath: dir)
        }
        tempDirs = []
    }

    private func makeTempDir() -> String {
        let path = NSTemporaryDirectory() + UUID().uuidString
        try! FileManager.default.createDirectory(atPath: path, withIntermediateDirectories: true)
        tempDirs.append(path)
        return path
    }

    private func makeSession() -> WorkflowSession {
        let profile = MediaProfile(
            type: .video,
            sourceDir: "/Volumes/TestCard/DCIM",
            readyDir: "/tmp/ready",
            gyroflowEnabled: true,
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(profile: profile, profileName: "test-profile")
        session.enabledSteps = Set(session.availableSteps)
        return session
    }

    func testDefaultState() {
        let session = makeSession()
        let (script, args) = session.buildPipelineArgs()

        XCTAssertEqual(script, "media-pipeline.sh")
        XCTAssertTrue(args.contains("--source"))
        XCTAssertTrue(args.contains("--profile"))
        XCTAssertFalse(args.contains("--source-action"))

        let tasksIndex = args.firstIndex(of: "--tasks")!
        let tasksSlice = args[(tasksIndex + 1)...]
            .prefix(while: { !$0.hasPrefix("--") })
        let tasks = Array(tasksSlice)
        XCTAssertTrue(tasks.contains("tag"))
        XCTAssertTrue(tasks.contains("fix-timestamp"))
        XCTAssertTrue(tasks.contains("gyroflow"))
        XCTAssertTrue(tasks.contains("archive-source"))
        XCTAssertFalse(tasks.contains("ingest"))
        XCTAssertFalse(tasks.contains("organize"))
    }

    func testAllOptionalStepsDisabled() {
        let session = makeSession()
        session.enabledSteps = Set(session.availableSteps.filter { $0.isAlwaysOn })
        let (script, args) = session.buildPipelineArgs()

        XCTAssertEqual(script, "media-pipeline.sh")
        XCTAssertFalse(args.contains("--tasks"))
        XCTAssertTrue(args.contains("--source"))
    }

    func testArchiveSourceWithDelete() {
        let session = makeSession()
        session.sourceAction = .delete
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("archive-source"))
        XCTAssertTrue(args.contains("delete"))
    }

    func testCopyCompanionFiles() {
        let session = makeSession()
        session.copyCompanionFiles = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--copy-companion-files"))
    }

    func testCopyCompanionFilesNotIncludedByDefault() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--copy-companion-files"))
    }

    func testTimezone() {
        let session = makeSession()
        session.timezone.value = "+0900"
        let (_, args) = session.buildPipelineArgs()

        let tzIndex = args.firstIndex(of: "--timezone")!
        XCTAssertEqual(args[tzIndex + 1], "+0900")
    }

    func testGroup() {
        let session = makeSession()
        session.group = "Japan"
        let (_, args) = session.buildPipelineArgs()

        let groupIndex = args.firstIndex(of: "--group")!
        XCTAssertEqual(args[groupIndex + 1], "Japan")
    }

    func testAppendTimezoneToGroup() {
        let session = makeSession()
        session.group = "Japan"
        session.timezone.value = "+0900"
        session.appendTimezoneToGroup = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--group"))
        XCTAssertTrue(args.contains("--append-timezone-to-group"))
        XCTAssertTrue(args.contains("--timezone"))
    }

    func testAppendTimezoneToGroupNotIncludedWhenDisabled() {
        let session = makeSession()
        session.group = "Japan"
        session.timezone.value = "+0900"
        session.appendTimezoneToGroup = false
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--group"))
        XCTAssertFalse(args.contains("--append-timezone-to-group"))
    }

    func testApplyMode() {
        let session = makeSession()
        session.applyMode = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--apply"))
    }

    func testApplyModeNotIncludedByDefault() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--apply"))
    }

    // MARK: - Step readiness

    func testIsStepReadyFixTimezoneRequiresTimezone() {
        let session = makeSession()
        session.timezone.value = ""
        XCTAssertFalse(session.isStepReady(.fixTimezone))
    }

    func testIsStepReadyFixTimezoneWithTimezone() {
        let session = makeSession()
        session.timezone.value = "+0900"
        XCTAssertTrue(session.isStepReady(.fixTimezone))
    }

    func testIsStepReadyIngestRequiresSourceDir() {
        let session = makeSession()
        session.sourceDir.value = ""
        XCTAssertFalse(session.isStepReady(.ingest))
    }

    func testAllStepsReadyWhenFixTimezoneDisabledAndTimezoneEmpty() {
        let session = makeSession()
        session.sourceDir.value = makeTempDir()
        session.readyDir.value = makeTempDir()
        session.timezone.value = ""
        session.enabledSteps.remove(.fixTimezone)
        XCTAssertTrue(session.allStepsReady)
    }

    func testAllStepsNotReadyWhenFixTimezoneEnabledAndTimezoneEmpty() {
        let session = makeSession()
        session.sourceDir.value = makeTempDir()
        session.readyDir.value = makeTempDir()
        session.timezone.value = ""
        session.enabledSteps.insert(.fixTimezone)
        XCTAssertFalse(session.allStepsReady)
    }

    func testAlwaysOnStepsNeverInTasks() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        if let tasksIndex = args.firstIndex(of: "--tasks") {
            let tasksSlice = args[(tasksIndex + 1)...]
                .prefix(while: { !$0.hasPrefix("--") })
            let tasks = Array(tasksSlice)
            XCTAssertFalse(tasks.contains("ingest"))
            XCTAssertFalse(tasks.contains("organize"))
        }
    }
}
