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
        let session = WorkflowSession(
            profile: profile, profileName: "test-profile", gyroflowAvailable: true
        )
        session.enabledSteps = Set(session.availableSteps)
        return session
    }

    func testDefaultState() {
        let profile = MediaProfile(
            type: .video,
            sourceDir: "/Volumes/TestCard/DCIM",
            readyDir: "/tmp/ready",
            gyroflowEnabled: true,
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(
            profile: profile, profileName: "test-profile", gyroflowAvailable: true
        )
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
        XCTAssertFalse(tasks.contains("archive-source"))
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

    func testArchiveSourceNotEnabledByDefault() {
        let profile = MediaProfile(
            type: .video,
            sourceDir: "/Volumes/TestCard/DCIM",
            readyDir: "/tmp/ready",
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(profile: profile, profileName: "test-profile")
        XCTAssertFalse(session.enabledSteps.contains(.archiveSource))
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
        session.timezone.value = "Asia/Tokyo"
        let (_, args) = session.buildPipelineArgs()

        let tzIndex = args.firstIndex(of: "--timezone")!
        XCTAssertEqual(args[tzIndex + 1], "Asia/Tokyo")
    }

    func testTimezoneKeepsIdentityAcrossZonesSharingAnOffset() {
        let session = makeSession()
        session.timezone.value = "Pacific/Auckland"
        XCTAssertEqual(session.timezoneOption?.city, "Auckland")
        XCTAssertEqual(session.timezoneOption?.offsets, TimezoneCatalog.option("Antarctica/McMurdo")?.offsets)

        let (_, args) = session.buildPipelineArgs()
        let tzIndex = args.firstIndex(of: "--timezone")!
        XCTAssertEqual(args[tzIndex + 1], "Pacific/Auckland")
    }

    func testUnknownTimezoneIsNotReady() {
        let session = makeSession()
        session.timezone.value = "+1200"
        XCTAssertFalse(session.isStepReady(.fixTimestamps))

        let (_, args) = session.buildPipelineArgs()
        XCTAssertFalse(args.contains("--timezone"))
    }

    func testGroup() {
        let session = makeSession()
        session.group = "Japan"
        let (_, args) = session.buildPipelineArgs()

        let groupIndex = args.firstIndex(of: "--group")!
        XCTAssertEqual(args[groupIndex + 1], "Japan")
    }

    func testGroupWithTimezone() {
        let session = makeSession()
        session.group = "Japan"
        session.timezone.value = "Asia/Tokyo"
        let (_, args) = session.buildPipelineArgs()

        let groupIndex = args.firstIndex(of: "--group")!
        XCTAssertEqual(args[groupIndex + 1], "Japan")
        XCTAssertTrue(args.contains("--timezone"))
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

    func testIsStepReadyFixTimestampsRequiresTimezone() {
        let session = makeSession()
        session.timezone.value = ""
        XCTAssertFalse(session.isStepReady(.fixTimestamps))
    }

    func testIsStepReadyFixTimestampsWithTimezone() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        XCTAssertTrue(session.isStepReady(.fixTimestamps))
    }

    func testIsStepReadyFixTimestampsPickerWithTimezone() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        XCTAssertTrue(session.isStepReady(.fixTimestamps))
    }

    func testIsStepReadyIngestRequiresSourceDir() {
        let session = makeSession()
        session.sourceDir.value = ""
        XCTAssertFalse(session.isStepReady(.ingest))
    }

    func testAllStepsReadyWhenFixTimestampsDisabledAndTimezoneEmpty() {
        let session = makeSession()
        session.sourceDir.value = makeTempDir()
        session.readyDir.value = makeTempDir()
        session.timezone.value = ""
        session.enabledSteps.remove(.fixTimestamps)
        XCTAssertTrue(session.allStepsReady)
    }

    func testAllStepsNotReadyWhenFixTimestampsEnabledAndTimezoneEmpty() {
        let session = makeSession()
        session.sourceDir.value = makeTempDir()
        session.readyDir.value = makeTempDir()
        session.timezone.value = ""
        session.enabledSteps.insert(.fixTimestamps)
        XCTAssertFalse(session.allStepsReady)
    }

    func testInferFromFilenames() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        session.inferFromFilenames = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--infer-from-filename"))
    }

    func testInferFromFilenamesNotIncludedByDefault() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--infer-from-filename"))
    }

    func testInferFromFilenamesNotIncludedWhenStepDisabled() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        session.inferFromFilenames = true
        session.enabledSteps.remove(.fixTimestamps)
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--infer-from-filename"))
    }

    func testTimeOffset() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        session.timeOffsetSeconds = 3600
        let (_, args) = session.buildPipelineArgs()

        let idx = args.firstIndex(of: "--time-offset")!
        XCTAssertEqual(args[idx + 1], "3600")
    }

    func testTimeOffsetNotIncludedWhenNil() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        session.timeOffsetSeconds = nil
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--time-offset"))
    }

    func testTimeOffsetNotIncludedWhenZero() {
        let session = makeSession()
        session.timezone.value = "Asia/Tokyo"
        session.timeOffsetSeconds = 0
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--time-offset"))
    }

    func testUpdateFilenameDates() {
        let session = makeSession()
        session.updateFilenameDates = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--update-filename-dates"))
    }

    func testUpdateFilenameDatesNotIncludedByDefault() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--update-filename-dates"))
    }

    func testForceTimezone() {
        let session = makeSession()
        session.forceTimezone = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--force-timezone"))
    }

    func testForceTimezoneNotIncludedByDefault() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--force-timezone"))
    }

    func testAllowMixedTimezones() {
        let session = makeSession()
        session.allowMixedTimezones = true
        let (_, args) = session.buildPipelineArgs()

        XCTAssertTrue(args.contains("--allow-mixed-timezones"))
    }

    func testAllowMixedTimezonesNotIncludedByDefault() {
        let session = makeSession()
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--allow-mixed-timezones"))
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

    // MARK: - Gyroflow preset

    func testGyroflowPresetIncludedWhenStepEnabled() {
        let session = makeSession()
        session.workingProfile.gyroflowSettings = StabilizationSettings(
            maxZoom: 110.0,
            adaptiveZoomWindow: 20.0,
            adaptiveZoomMethod: 1
        )
        let (_, args) = session.buildPipelineArgs()

        let idx = args.firstIndex(of: "--gyroflow-preset")
        XCTAssertNotNil(idx)
        let json = args[idx! + 1]
        XCTAssertTrue(json.contains("max_zoom"))
        XCTAssertTrue(json.contains("adaptive_zoom_window"))
        XCTAssertTrue(json.contains("adaptive_zoom_method"))
    }

    func testGyroflowPresetNotIncludedWhenStepDisabled() {
        let session = makeSession()
        session.enabledSteps.remove(.gyroflow)
        session.workingProfile.gyroflowSettings = StabilizationSettings(maxZoom: 110.0)
        let (_, args) = session.buildPipelineArgs()

        XCTAssertFalse(args.contains("--gyroflow-preset"))
    }

    func testGyroflowPresetOmitsNilValues() {
        let session = makeSession()
        session.workingProfile.gyroflowSettings = StabilizationSettings(adaptiveZoomMethod: 2)
        let (_, args) = session.buildPipelineArgs()

        let idx = args.firstIndex(of: "--gyroflow-preset")!
        let json = args[idx + 1]
        XCTAssertFalse(json.contains("max_zoom"))
        XCTAssertFalse(json.contains("adaptive_zoom_window"))
        XCTAssertTrue(json.contains("adaptive_zoom_method"))
    }

    // MARK: - Gyroflow session initialization

    func testGyroflowSettingsCarriedFromProfile() {
        let profile = MediaProfile(
            type: .video,
            gyroflowEnabled: true,
            gyroflowSettings: StabilizationSettings(
                maxZoom: 105.0,
                adaptiveZoomWindow: 15.0,
                adaptiveZoomMethod: 1
            ),
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(profile: profile, profileName: "test")

        XCTAssertEqual(session.workingProfile.gyroflowSettings?.maxZoom, 105.0)
        XCTAssertEqual(session.workingProfile.gyroflowSettings?.adaptiveZoomWindow, 15.0)
        XCTAssertEqual(session.workingProfile.gyroflowSettings?.adaptiveZoomMethod, 1)
    }

    func testGyroflowSettingsNilWhenProfileHasNone() {
        let profile = MediaProfile(type: .video, gyroflowEnabled: true, fileExtensions: [".mp4"])
        let session = WorkflowSession(profile: profile, profileName: "test")

        XCTAssertNil(session.workingProfile.gyroflowSettings)
    }
}
