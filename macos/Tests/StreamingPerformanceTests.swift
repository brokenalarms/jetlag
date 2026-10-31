import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// A run streams thousands of log lines and hundreds of rows into the panel. Each of
/// those must cost the same whether it is the 10th or the 3,000th: any per-update
/// work proportional to what is already shown (rebuilding the transcript, re-measuring
/// every row) makes the app fall behind the pipeline on a real card and turns Cancel
/// into a no-op while the backlog drains. These tests pin the cost to linear and pin
/// the incremental rendering that keeps it there.
final class StreamingPerformanceTests: XCTestCase {

    // MARK: - Fixtures

    private func row(_ i: Int) -> DiffTableRow {
        var row = DiffTableRow(file: "VID_20250815_17\(String(format: "%04d", i))_00_\(String(format: "%03d", i)).insv")
        row.originalTime = "2025:08:15 17:38:5\(i % 10)+09:00"
        row.correctedTime = "2025:08:15 17:38:5\(i % 10)+09:00"
        row.originalEpoch = 1_755_000_000 + Double(i * 60)
        row.correctedEpoch = 1_755_000_000 + Double(i * 60)
        row.timestampAction = "would_fix"
        row.timestampSource = TimestampSource(rawValue: "datetimeoriginal")
        row.dest = "/Volumes/Media/Ready/2025/2025-08-15/\(row.file)"
        row.organizeAction = "skipped"
        row.organizeReason = "exists_differs"
        row.pipelineResult = "would_change"
        row.staleFields = ["Keys:CreationDate", "QuickTime:CreateDate"]
        return row
    }

    private func hostedWindow(_ state: AppState) -> (NSHostingView<ContentView>, NSWindow) {
        state.showLogOutput = true
        return HostedWindow.make(state)
    }

    private struct StreamCost {
        var wall: TimeInterval
        var cpu: TimeInterval
    }

    private struct StreamCostSample: Encodable {
        let recordedAt: String
        let firstWall: TimeInterval
        let secondWall: TimeInterval
        let firstCPU: TimeInterval
        let secondCPU: TimeInterval
        let loadBefore: Double
        let loadAfter: Double
    }

    private func mainThreadCPUTime() -> TimeInterval {
        var time = timespec()
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &time)
        return TimeInterval(time.tv_sec) + TimeInterval(time.tv_nsec) / 1_000_000_000
    }

    private func oneMinuteLoad() -> Double {
        var load = 0.0
        getloadavg(&load, 1)
        return load
    }

    /// Streams `count` rows, each followed by eight log lines, through the hosted
    /// window one update at a time, and returns the cost of the first and second halves.
    private func streamHalves(count: Int) -> (first: StreamCost, second: StreamCost) {
        let state = AppState()
        let (host, _) = hostedWindow(state)

        func stream(_ range: Range<Int>) -> StreamCost {
            let wallStart = Date()
            let cpuStart = mainThreadCPUTime()
            for i in range {
                state.diffTableRows.append(row(i))
                for k in 0..<8 {
                    state.logOutput.append(LogLine(
                        text: "\u{1B}[36m🔍 line \(i).\(k)\u{1B}[0m 📊 Change: Keys:CreationDate (missing)",
                        stream: .stderr))
                    RunLoop.main.run(until: Date())
                }
                host.layoutSubtreeIfNeeded()
            }
            return StreamCost(wall: Date().timeIntervalSince(wallStart), cpu: mainThreadCPUTime() - cpuStart)
        }
        // Warm-up absorbs first-layout costs so neither half pays them.
        _ = stream(0..<8)
        let first = stream(8..<(8 + count / 2))
        let second = stream((8 + count / 2)..<(8 + count))
        return (first, second)
    }

    /// One JSON line per run in ~/Library/Logs/Jetlag, outside the repo so it outlives
    /// worktree resets. This test fails on some busy runs, and these samples are the
    /// evidence for why: its measure and threshold stay as they are until they are read.
    private func record(_ sample: StreamCostSample) throws {
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Jetlag", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("streaming-cost.jsonl")
        if !FileManager.default.fileExists(atPath: file.path) {
            FileManager.default.createFile(atPath: file.path, contents: nil)
        }
        let line = try JSONEncoder().encode(sample) + Data("\n".utf8)
        let handle = try FileHandle(forWritingTo: file)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: line)
    }

    // MARK: - Linear cost

    /// The second half of a run must not cost materially more than the first. With
    /// per-update work proportional to the rows and lines already shown, the second
    /// half of 160 rows cost ~3× the first; linear rendering keeps the two equal
    /// within noise.
    func testSecondHalfOfARunCostsNoMoreThanTheFirst() throws {
        let loadBefore = oneMinuteLoad()
        let (first, second) = streamHalves(count: 160)
        try record(StreamCostSample(
            recordedAt: ISO8601DateFormatter().string(from: Date()),
            firstWall: first.wall, secondWall: second.wall,
            firstCPU: first.cpu, secondCPU: second.cpu,
            loadBefore: loadBefore, loadAfter: oneMinuteLoad()))
        XCTAssertLessThanOrEqual(
            second.wall, first.wall * 1.3 + 0.2,
            String(format: "first half %.2fs, second half %.2fs — per-update cost is growing with the run", first.wall, second.wall))
    }

    /// Streams rows, each followed by eight log lines, through the real window one update
    /// at a time. Re-rendering any earlier text makes the characters edited exceed the
    /// characters shown, so the count pins the cost to linear on any machine, however
    /// busy: comparing wall time failed whenever other work was running.
    func testEveryLogCharacterIsRenderedOnceAcrossARun() throws {
        let state = AppState()
        let (host, _) = hostedWindow(state)
        let textView = try XCTUnwrap(HostedWindow.logScrollView(in: host)?.documentView as? NSTextView)
        let storage = try XCTUnwrap(textView.textStorage)

        var editedCharacters = 0
        let observer = NotificationCenter.default.addObserver(
            forName: NSTextStorage.didProcessEditingNotification, object: storage, queue: nil
        ) { _ in
            // AppKit restyles text it already holds, which replaces no characters.
            if storage.editedMask.contains(.editedCharacters) {
                editedCharacters += storage.editedRange.length
            }
        }
        defer { NotificationCenter.default.removeObserver(observer) }

        for i in 0..<40 {
            state.diffTableRows.append(row(i))
            for k in 0..<8 {
                state.logOutput.append(LogLine(
                    text: "\u{1B}[36m🔍 line \(i).\(k)\u{1B}[0m 📊 Change: Keys:CreationDate (missing)",
                    stream: .stderr))
                RunLoop.main.run(until: Date())
            }
            host.layoutSubtreeIfNeeded()
        }
        HostedWindow.settle(host)

        XCTAssertEqual(state.logViewHolder.renderedCount, state.logOutput.count)
        XCTAssertEqual(editedCharacters, storage.length)
    }

    /// The table recomputes its column widths on every update, over every row so far.
    /// Each row's text must still be measured once, whether it is the 10th or the 160th.
    func testEveryRowIsMeasuredOnceAcrossARun() {
        let cache = RowMeasurements()
        var rows: [DiffTableRow] = []
        for i in 0..<160 {
            rows.append(row(i))
            _ = cache.columnWidths(for: rows, texts: texts)
        }
        XCTAssertEqual(cache.measurementCount, rows.count)
    }

    // MARK: - Incremental log rendering

    private func storage() -> (NSTextStorage, LogViewHolder) {
        let scrollView = LogScrollView.make()
        let textView = scrollView.documentView as! NSTextView
        return (textView.textStorage!, LogViewHolder())
    }

    /// Only the lines added since the last render are appended, and the rendered
    /// transcript is exactly the stripped lines joined by newlines.
    func testLogRenderAppendsOnlyNewLines() {
        let (storage, holder) = storage()
        var lines = [LogLine(text: "\u{1B}[36mone\u{1B}[0m", stream: .stderr)]
        LogTextView.render(lines, into: storage, holder: holder)
        XCTAssertEqual(storage.string, "one")

        lines.append(LogLine(text: "two", stream: .stdout))
        lines.append(LogLine(text: "three", stream: .stderr))
        var changes = 0
        LogTextView.render(lines, into: storage, holder: holder) { changes += 1; return {} }
        XCTAssertEqual(storage.string, "one\ntwo\nthree")
        XCTAssertEqual(changes, 1)

        LogTextView.render(lines, into: storage, holder: holder) { changes += 1; return {} }
        XCTAssertEqual(changes, 1, "an update with nothing new must touch nothing")
        XCTAssertEqual(holder.renderedCount, 3)
    }

    /// A cleared transcript (fewer lines than rendered) is rebuilt from scratch.
    func testLogRenderRebuildsAfterClear() {
        let (storage, holder) = storage()
        LogTextView.render((0..<5).map { LogLine(text: "line \($0)", stream: .stderr) },
                           into: storage, holder: holder)
        LogTextView.render([LogLine(text: "fresh", stream: .stderr)], into: storage, holder: holder)
        XCTAssertEqual(storage.string, "fresh")
        XCTAssertEqual(holder.renderedCount, 1)
    }

    /// ANSI stripping happens once, when the line is created, not on every render.
    func testStrippedTextIsComputedAtIngest() {
        let line = LogLine(text: "\u{1B}[36m🔍 VID.insv\u{1B}[0m", stream: .stderr)
        XCTAssertEqual(line.strippedText, "🔍 VID.insv")
        XCTAssertEqual(LogTextView.displayText(for: [line]), "🔍 VID.insv")
    }

    // MARK: - Cancel drops the backlog

    /// Cancel must stop the UI, not just the process: lines the pipeline had already
    /// written are still queued in the stream, and draining them after a cancel is
    /// what made Cancel look inert.
    func testCancelStopsConsumingBufferedLines() async {
        let state = AppState()
        let (stream, continuation) = AsyncStream<LogLine>.makeStream()
        for i in 0..<50 {
            continuation.yield(LogLine(text: "line \(i)", stream: .stderr))
        }
        continuation.finish()

        let consumed = expectation(description: "consumer observed")
        consumed.assertForOverFulfill = false
        state.isRunning = true
        state.currentRunTask = Task {
            for await line in stream {
                if Task.isCancelled { break }
                await MainActor.run {
                    state.appendLog(line)
                    if state.logOutput.count == 5 { state.cancelRunning() }
                }
                consumed.fulfill()
            }
        }
        await fulfillment(of: [consumed], timeout: 2)
        try? await Task.sleep(nanoseconds: 100_000_000)

        await MainActor.run {
            XCTAssertLessThanOrEqual(state.logOutput.count, 6, "lines buffered before the cancel must not keep arriving")
            XCTAssertFalse(state.isRunning)
            XCTAssertNil(state.currentRunTask)
        }
    }

    // MARK: - Row measurement cache

    private func texts(_ row: DiffTableRow) -> [CellText] {
        let mono = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        return [CellText([(row.file, mono)]), CellText([(row.correctedTime ?? "", mono)])]
    }

    /// A run's live row is appended sparse and filled in as its events arrive, then
    /// replaced by the finalised row at the same index. Measuring a row once by
    /// position left the columns sized to the empty row; the cache must re-measure a
    /// row whose text changed and leave the others alone.
    func testRowFilledInAfterAppendIsReMeasuredAndUnchangedRowsAreNot() {
        let cache = RowMeasurements()
        var sparse = DiffTableRow(file: "a.mp4")
        let narrow = cache.columnWidths(for: [sparse], texts: texts)
        XCTAssertEqual(cache.measurementCount, 1)

        sparse.correctedTime = "2025:08:15 17:38:54+09:00"
        let filled = cache.columnWidths(for: [sparse], texts: texts)
        XCTAssertEqual(cache.measurementCount, 2, "a row whose text changed is measured again")
        XCTAssertGreaterThan(filled.fitted[1], narrow.fitted[1], "the column grows to the filled row")

        let untouched = cache.columnWidths(for: [sparse, DiffTableRow(file: "b.mp4")], texts: texts)
        XCTAssertEqual(cache.measurementCount, 3, "only the new row is measured; the unchanged one is not")
        XCTAssertEqual(untouched.fitted[1], filled.fitted[1])

        _ = cache.columnWidths(for: [sparse, DiffTableRow(file: "b.mp4")], texts: texts)
    }

    /// Clearing the table (fewer rows than measured) drops the stale maxima.
    func testClearedTableRebuildsTheMaxima() {
        let cache = RowMeasurements()
        var wide = DiffTableRow(file: "a-very-long-file-name-that-widens-the-column.mp4")
        wide.correctedTime = "2025:08:15 17:38:54+09:00"
        let before = cache.columnWidths(for: [wide], texts: texts)
        let after = cache.columnWidths(for: [DiffTableRow(file: "b.mp4")], texts: texts)
        XCTAssertLessThan(after.fitted[0], before.fitted[0])
    }
}
