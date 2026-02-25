import XCTest
@testable import Jetlag

final class PipelineArgsTests: XCTestCase {

    private func makeState() -> AppState {
        let state = AppState()
        state.selectedProfile = "test-profile"
        state.sourceDir = "/tmp"
        state.readyDir = "/tmp"
        state.profilesConfig = ProfilesConfig(
            gyroflow: nil,
            backupConfig: nil,
            profiles: [
                "test-profile": MediaProfile(
                    type: .video,
                    sourceDir: "/tmp",
                    readyDir: "/tmp",
                    gyroflowEnabled: true,
                    fileExtensions: [".mp4"]
                )
            ]
        )
        state.enabledSteps = Set(state.availableSteps)
        return state
    }

    func testDefaultState() {
        let state = makeState()
        let (script, args) = state.buildPipelineArgs()

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
        let state = makeState()
        state.enabledSteps = Set(state.availableSteps.filter { $0.isAlwaysOn })
        let (script, args) = state.buildPipelineArgs()

        XCTAssertEqual(script, "media-pipeline.sh")
        XCTAssertFalse(args.contains("--tasks"))
        XCTAssertTrue(args.contains("--source"))
    }

    func testArchiveSourceWithDelete() {
        let state = makeState()
        state.sourceAction = .delete
        let (_, args) = state.buildPipelineArgs()

        XCTAssertTrue(args.contains("archive-source"))
        XCTAssertTrue(args.contains("delete"))
    }

    func testCopyCompanionFiles() {
        let state = makeState()
        state.copyCompanionFiles = true
        let (_, args) = state.buildPipelineArgs()

        XCTAssertTrue(args.contains("--copy-companion-files"))
    }

    func testCopyCompanionFilesNotIncludedByDefault() {
        let state = makeState()
        let (_, args) = state.buildPipelineArgs()

        XCTAssertFalse(args.contains("--copy-companion-files"))
    }

    func testTimezone() {
        let state = makeState()
        state.timezone = "+0900"
        let (_, args) = state.buildPipelineArgs()

        let tzIndex = args.firstIndex(of: "--timezone")!
        XCTAssertEqual(args[tzIndex + 1], "+0900")
    }

    func testGroup() {
        let state = makeState()
        state.group = "Japan"
        let (_, args) = state.buildPipelineArgs()

        let groupIndex = args.firstIndex(of: "--group")!
        XCTAssertEqual(args[groupIndex + 1], "Japan")
    }

    func testAppendTimezoneToGroup() {
        let state = makeState()
        state.group = "Japan"
        state.timezone = "+0900"
        state.appendTimezoneToGroup = true
        let (_, args) = state.buildPipelineArgs()

        XCTAssertTrue(args.contains("--group"))
        XCTAssertTrue(args.contains("--append-timezone-to-group"))
        XCTAssertTrue(args.contains("--timezone"))
    }

    func testAppendTimezoneToGroupNotIncludedWhenDisabled() {
        let state = makeState()
        state.group = "Japan"
        state.timezone = "+0900"
        state.appendTimezoneToGroup = false
        let (_, args) = state.buildPipelineArgs()

        XCTAssertTrue(args.contains("--group"))
        XCTAssertFalse(args.contains("--append-timezone-to-group"))
    }

    func testApplyMode() {
        let state = makeState()
        state.applyMode = true
        let (_, args) = state.buildPipelineArgs()

        XCTAssertTrue(args.contains("--apply"))
    }

    func testApplyModeNotIncludedByDefault() {
        let state = makeState()
        let (_, args) = state.buildPipelineArgs()

        XCTAssertFalse(args.contains("--apply"))
    }

    // MARK: - Step readiness

    func testIsStepReadyFixTimezoneRequiresTimezone() {
        let state = makeState()
        state.timezone = ""
        XCTAssertFalse(state.isStepReady(.fixTimezone))
    }

    func testIsStepReadyFixTimezoneWithTimezone() {
        let state = makeState()
        state.timezone = "+0900"
        XCTAssertTrue(state.isStepReady(.fixTimezone))
    }

    func testIngestNotReadyWhenSourceDirEmpty() {
        let state = makeState()
        state.sourceDir = ""
        XCTAssertFalse(state.isStepReady(.ingest))
    }

    func testIngestNotReadyWhenSourceDirNotExists() {
        let state = makeState()
        state.sourceDir = "/nonexistent/path/that/does/not/exist"
        XCTAssertFalse(state.isStepReady(.ingest))
    }

    func testOrganizeNotReadyWhenReadyDirEmpty() {
        let state = makeState()
        state.readyDir = ""
        XCTAssertFalse(state.isStepReady(.organize))
    }

    func testOrganizeNotReadyWhenReadyDirNotExists() {
        let state = makeState()
        state.readyDir = "/nonexistent/path/that/does/not/exist"
        XCTAssertFalse(state.isStepReady(.organize))
    }

    func testAllStepsReadyWhenFixTimezoneDisabledAndTimezoneEmpty() {
        let state = makeState()
        state.timezone = ""
        state.enabledSteps.remove(.fixTimezone)
        XCTAssertTrue(state.allStepsReady)
    }

    func testAllStepsNotReadyWhenFixTimezoneEnabledAndTimezoneEmpty() {
        let state = makeState()
        state.timezone = ""
        state.enabledSteps.insert(.fixTimezone)
        XCTAssertFalse(state.allStepsReady)
    }

    func testAlwaysOnStepsNeverInTasks() {
        let state = makeState()
        let (_, args) = state.buildPipelineArgs()

        if let tasksIndex = args.firstIndex(of: "--tasks") {
            let tasksSlice = args[(tasksIndex + 1)...]
                .prefix(while: { !$0.hasPrefix("--") })
            let tasks = Array(tasksSlice)
            XCTAssertFalse(tasks.contains("ingest"))
            XCTAssertFalse(tasks.contains("organize"))
        }
    }
}
