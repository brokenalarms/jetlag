import XCTest
@testable import Jetlag

/// A run has to finish when the script finishes. The pipeline's descendants —
/// jetlag-metadata and the `exiftool -stay_open` it owns — inherit the script's
/// stdout and stderr, so one that outlives the script holds the pipe write ends
/// open and EOF never arrives. Completion therefore follows the script's exit:
/// otherwise the log stream never ends, `finishRun` never runs, and the app is
/// left with no completion popup, the mode stuck on Apply, and Run disabled.
final class RunCompletionTests: XCTestCase {
    private var temporaryDirectories: [URL] = []
    private var lingeringProcesses: [pid_t] = []

    override func tearDown() {
        for pid in lingeringProcesses where pid > 0 {
            kill(pid, SIGKILL)
        }
        lingeringProcesses = []
        for directory in temporaryDirectories {
            try? FileManager.default.removeItem(at: directory)
        }
        temporaryDirectories = []
        super.tearDown()
    }

    /// The script exits while a child it backgrounded still holds fd 1 and 2 —
    /// the shape a wedged exiftool leaves behind. The stream must end with the
    /// script rather than with the child two minutes later, and the summary the
    /// script printed just before exiting must still arrive.
    func testStreamFinishesWhenScriptExitsWhileADescendantHoldsThePipesOpen() async throws {
        let temp = try makeTemporaryDirectory()
        try writeScript("""
        #!/bin/bash
        /bin/sleep 120 &
        /bin/echo "descendant $!" >&2
        /bin/echo '{"event":"pipeline_summary","files_changed":1}'
        """, named: "linger.sh", in: temp)

        let (process, stream) = ScriptRunner.run(
            script: "linger.sh", args: [], workingDir: temp.path, profilesPath: "")
        let lines = await collectLines(from: stream, timeout: 10)
        process.terminateGroup(gracePeriod: 0)

        let delivered = try XCTUnwrap(
            lines, "the stream never finished — it is still waiting for the descendant's EOF")
        if let descendant = delivered.first(where: { $0.hasPrefix("descendant ") })
            .flatMap({ pid_t($0.dropFirst("descendant ".count)) }) {
            lingeringProcesses.append(descendant)
        }
        XCTAssertTrue(
            delivered.contains("{\"event\":\"pipeline_summary\",\"files_changed\":1}"),
            "Actual: \(delivered), Expected: the summary printed before the exit")
    }

    /// The ordinary run is unchanged: nothing outlives the script, every line is
    /// delivered, and the stream finishes on EOF as before.
    func testStreamDeliversEveryLineWhenNothingOutlivesTheScript() async throws {
        let temp = try makeTemporaryDirectory()
        try writeScript("""
        #!/bin/bash
        /bin/echo first
        /bin/echo second >&2
        /bin/echo '{"event":"pipeline_summary","files_changed":2}'
        """, named: "plain.sh", in: temp)

        let (_, stream) = ScriptRunner.run(
            script: "plain.sh", args: [], workingDir: temp.path, profilesPath: "")
        let lines = await collectLines(from: stream, timeout: 10)
        let delivered = try XCTUnwrap(lines, "the stream never finished")

        XCTAssertEqual(
            Set(delivered),
            ["first", "second", "{\"event\":\"pipeline_summary\",\"files_changed\":2}"],
            "Actual: \(delivered)")
    }

    /// The script's last line may arrive without a trailing newline — a summary
    /// written with `printf`, or output cut short by cancel. It is still a line
    /// and must reach the log rather than being dropped with the read buffer.
    func testFinalLineWithoutATrailingNewlineIsDelivered() async throws {
        let temp = try makeTemporaryDirectory()
        try writeScript("""
        #!/bin/bash
        /bin/echo complete
        printf '{"event":"pipeline_summary","files_changed":3}'
        """, named: "unterminated.sh", in: temp)

        let (_, stream) = ScriptRunner.run(
            script: "unterminated.sh", args: [], workingDir: temp.path, profilesPath: "")
        let lines = await collectLines(from: stream, timeout: 10)
        let delivered = try XCTUnwrap(lines, "the stream never finished")

        XCTAssertEqual(
            delivered, ["complete", "{\"event\":\"pipeline_summary\",\"files_changed\":3}"],
            "Actual: \(delivered)")
    }

    /// Collect every non-empty line, or `nil` if the stream has not finished
    /// within `timeout` — the hang this covers is an absence of completion, so a
    /// bounded wait is the only way to observe it.
    private func collectLines(
        from stream: AsyncStream<LogLine>, timeout: TimeInterval
    ) async -> [String]? {
        await withTaskGroup(of: [String]?.self) { group in
            group.addTask {
                var lines: [String] = []
                for await line in stream where !line.strippedText.isEmpty {
                    lines.append(line.strippedText)
                }
                return Task.isCancelled ? nil : lines
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                return nil
            }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
    }

    private func writeScript(_ body: String, named name: String, in directory: URL) throws {
        let url = directory.appendingPathComponent(name)
        try body.write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
    }

    private func makeTemporaryDirectory() throws -> URL {
        let url = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("jetlag-run-completion-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        temporaryDirectories.append(url)
        return url
    }
}
