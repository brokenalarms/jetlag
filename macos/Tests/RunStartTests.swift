import XCTest
@testable import Jetlag

/// The media count that gates a run is a script launch, so it answers some time after
/// Run is pressed. These tests hold that answer back to cover what happens around it:
/// the run is already underway while waiting, the free-tier limit stops an over-limit
/// run, a failed count never blocks one, and cancelling while waiting starts nothing.
final class RunStartTests: XCTestCase {

    private var state: AppState!
    private var answer: AsyncStream<Int?>.Continuation!
    private var answers: AsyncStream<Int?>!
    private var started = 0
    private var overLimitCounts: [Int] = []

    override func setUp() {
        state = AppState()
        (answers, answer) = AsyncStream.makeStream(of: Int?.self)
        started = 0
        overLimitCounts = []
    }

    private func pressRun(limit: Int = 10) -> Task<Void, Never>? {
        let answers = self.answers!
        state.startRun(
            afterCounting: {
                for await count in answers { return count }
                return nil
            },
            exceedsLimit: { $0 > limit },
            onOverLimit: { self.overLimitCounts.append($0) },
            start: { self.started += 1 })
        return state.currentRunTask
    }

    /// Until the count answers, Run is disabled and the form inert, which is what stops
    /// a second press starting a second pipeline. Nothing has been launched yet.
    func testTheRunIsUnderwayWhileTheCountIsTaken() async {
        let run = pressRun()

        XCTAssertTrue(state.isRunning)
        XCTAssertEqual(started, 0)

        answer.yield(3)
        await run?.value
    }

    func testACountWithinTheLimitStartsTheRun() async {
        let run = pressRun()

        answer.yield(10)
        await run?.value

        XCTAssertEqual(started, 1)
        XCTAssertEqual(overLimitCounts, [])
    }

    /// An over-limit run reports its count for the upgrade prompt, starts nothing, and
    /// leaves the form usable.
    func testACountOverTheLimitStartsNothing() async {
        let run = pressRun()

        answer.yield(11)
        await run?.value

        XCTAssertEqual(started, 0)
        XCTAssertEqual(overLimitCounts, [11])
        XCTAssertFalse(state.isRunning)
        XCTAssertNil(state.currentRunTask)
    }

    /// The limit must never stop a run because the count itself failed.
    func testAFailedCountStartsTheRun() async {
        let run = pressRun()

        answer.yield(nil)
        await run?.value

        XCTAssertEqual(started, 1)
        XCTAssertEqual(overLimitCounts, [])
    }

    /// Cancel is on offer while the count is taken; pressing it must not be undone by
    /// the count answering afterwards.
    func testCancellingDuringTheCountStartsNothing() async {
        let run = pressRun()

        state.cancelRunning()
        answer.yield(3)
        await run?.value

        XCTAssertEqual(started, 0)
        XCTAssertEqual(overLimitCounts, [])
        XCTAssertFalse(state.isRunning)
    }
}
