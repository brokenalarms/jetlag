import XCTest
@testable import Jetlag

final class ArchiveSourceHelpTextTests: XCTestCase {
    func testPipelineHelpStatesArchiveRunsOnceAfterEveryFile() {
        let help = Strings.Pipeline.archiveSourceHelp
        XCTAssertTrue(help.contains("once every file has been processed"),
            "should state the step runs once after every file has been processed")
        XCTAssertTrue(help.contains("cancelled or failed run archives nothing"),
            "should state a cancelled or failed run archives nothing")
    }

    func testWorkflowHelpKeepsBulletsAndStatesRunsOnceAfterBatch() {
        let help = Strings.Workflow.archiveSourceHelp
        XCTAssertTrue(help.contains("• Destination"),
            "should explain the destination field")
        XCTAssertTrue(help.contains("• Rename source dir"),
            "should explain the rename checkbox")
        XCTAssertTrue(help.contains("Runs once, after the whole batch"),
            "should append the runs-once-after-the-whole-batch line")
        XCTAssertTrue(help.contains("re-run the folder to finish and archive it"),
            "should explain how to recover after a cancelled or failed run")
    }
}
