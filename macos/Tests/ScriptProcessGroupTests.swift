import XCTest
@testable import Jetlag

/// A launched pipeline is a tree — bash execs Python, which owns jetlag-metadata,
/// which owns `exiftool -stay_open`. Signalling only the script leaves the rest
/// re-parented to launchd and still running, so the app puts every run in its own
/// process group and cancel signals the group.
final class ScriptProcessGroupTests: XCTestCase {
    private var temporaryDirectories: [URL] = []

    override func tearDown() {
        for directory in temporaryDirectories {
            try? FileManager.default.removeItem(at: directory)
        }
        temporaryDirectories = []
        super.tearDown()
    }

    /// The script leads a process group of its own rather than joining the app's,
    /// which is what makes a single signal able to reach everything it spawned.
    func testScriptLeadsItsOwnProcessGroup() async throws {
        let temp = try makeTemporaryDirectory()
        try writeScript("#!/bin/bash\n/bin/ps -o pgid= -p $$\n", named: "report-pgid.sh", in: temp)

        let (process, stream) = ScriptRunner.run(
            script: "report-pgid.sh", args: [], workingDir: temp.path, profilesPath: "")
        var lines: [String] = []
        for await line in stream where !line.strippedText.isEmpty {
            lines.append(line.strippedText)
        }
        process.waitUntilExit()

        let reportedGroup = try XCTUnwrap(pid_t(try XCTUnwrap(lines.first)))
        XCTAssertEqual(reportedGroup, process.processIdentifier,
                       "the script should lead the group, so its pgid is its own pid")
        XCTAssertNotEqual(reportedGroup, getpgid(0),
                          "the script must not run in the app's process group")
    }

    /// Cancelling reaches the descendants, not just the script: a child that
    /// outlives its parent — as jetlag-metadata and exiftool do — is signalled too.
    func testTerminateGroupStopsDescendantsThatOutliveTheScript() async throws {
        let temp = try makeTemporaryDirectory()
        // The script exits immediately, leaving the sleep re-parented — exactly the
        // shape that left orphaned exiftool processes behind.
        // The descendant's output goes to /dev/null: inheriting the script's pipes
        // would hold them open past the script's own exit and the stream would
        // never finish.
        try writeScript("#!/bin/bash\n/bin/sleep 120 >/dev/null 2>&1 &\necho $!\n",
                        named: "spawn-orphan.sh", in: temp)

        let (process, stream) = ScriptRunner.run(
            script: "spawn-orphan.sh", args: [], workingDir: temp.path, profilesPath: "")
        var lines: [String] = []
        for await line in stream where !line.strippedText.isEmpty {
            lines.append(line.strippedText)
        }
        let orphan = try XCTUnwrap(pid_t(try XCTUnwrap(lines.first)))
        XCTAssertEqual(kill(orphan, 0), 0, "the descendant should still be running before cancel")

        process.terminateGroup(gracePeriod: 0.1)

        let descendantStopped = await waitForExit(of: orphan)
        XCTAssertTrue(descendantStopped, "the descendant survived cancel")
    }

    /// Cancel is the app's Ctrl+C: the group is interrupted, not terminated, so
    /// every member sees the signal a foreground job would see from a terminal —
    /// and anything that ignores it is still killed once the grace period is up.
    func testTerminateGroupInterruptsBeforeKilling() async throws {
        let temp = try makeTemporaryDirectory()
        let received = temp.appendingPathComponent("received-signal")
        let started = temp.appendingPathComponent("started")
        // The script records which signal it got and then keeps running, so the
        // kill fallback is exercised by the same run that proves the signal.
        try writeScript("""
        #!/bin/bash
        trap '/bin/echo INT >> "\(received.path)"' INT
        trap '/bin/echo TERM >> "\(received.path)"' TERM
        /usr/bin/touch "\(started.path)"
        while true; do /bin/sleep 0.1; done
        """, named: "record-signal.sh", in: temp)

        let (process, _) = ScriptRunner.run(
            script: "record-signal.sh", args: [], workingDir: temp.path, profilesPath: "")
        let running = await waitFor { FileManager.default.fileExists(atPath: started.path) }
        XCTAssertTrue(running, "the script never started")

        process.terminateGroup(gracePeriod: 0.5)

        let recorded = await waitFor {
            (try? String(contentsOf: received, encoding: .utf8))?.contains("INT") == true
        }
        let signals = (try? String(contentsOf: received, encoding: .utf8)) ?? ""
        XCTAssertTrue(recorded, "Actual: script received \"\(signals)\", Expected: INT")

        let killed = await waitForExit(of: process.processIdentifier)
        XCTAssertTrue(killed, "a script that ignores the interrupt must still be killed")
    }

    private func waitFor(_ condition: () -> Bool, timeout: TimeInterval = 5) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        return condition()
    }

    private func waitForExit(of pid: pid_t, timeout: TimeInterval = 5) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if kill(pid, 0) != 0 { return true }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        return kill(pid, 0) != 0
    }

    private func writeScript(_ body: String, named name: String, in directory: URL) throws {
        let url = directory.appendingPathComponent(name)
        try body.write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
    }

    private func makeTemporaryDirectory() throws -> URL {
        let url = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("jetlag-process-group-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        temporaryDirectories.append(url)
        return url
    }
}
