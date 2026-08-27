import XCTest

/// A build made in a worktree under `.ralph/` must never be able to pass itself
/// off as the installed Jetlag: the same bundle id, product name and Application
/// Support folder would mean shared UserDefaults, a shared Launch Services
/// registration, a shared profiles file and the same name in the Dock. The
/// identity is parameterised instead, and this guard — run by the "Guard
/// Worktree Bundle Identity" pre-build phase — is what stops a worktree build
/// that forgot to pass the suffixes.
final class WorktreeBundleIdentityGuardTests: XCTestCase {

    private static let guardScript = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .appendingPathComponent("BuildScripts/guard-worktree-identity.sh")

    private struct GuardRun {
        let status: Int32
        let output: String
    }

    private func runGuard(projectDir: String, bundleSuffix: String?) throws -> GuardRun {
        let process = Process()
        process.executableURL = Self.guardScript
        var environment = ["PROJECT_DIR": projectDir]
        if let bundleSuffix {
            environment["JETLAG_BUNDLE_SUFFIX"] = bundleSuffix
        }
        process.environment = environment
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        return GuardRun(status: process.terminationStatus,
                        output: String(data: data, encoding: .utf8) ?? "")
    }

    /// The failure the guard exists for: a worktree build with no suffix is
    /// stopped before it can produce a bundle that collides with the installed
    /// app, and the message names the variables that unblock it.
    func testWorktreeBuildWithoutASuffixFails() throws {
        let result = try runGuard(
            projectDir: "/Users/someone/Developer/jetlag/.ralph/worktrees/ralph-1/macos",
            bundleSuffix: nil)

        XCTAssertNotEqual(result.status, 0, "an unsuffixed build under .ralph/ must not proceed")
        XCTAssertTrue(result.output.contains("error:"),
                      "Xcode only surfaces a build phase failure it can parse: \(result.output)")
        XCTAssertTrue(result.output.contains("JETLAG_BUNDLE_SUFFIX"),
                      "the message has to name the variable to pass: \(result.output)")
        XCTAssertTrue(result.output.contains("JETLAG_PRODUCT_SUFFIX"),
                      "the message has to name the variable to pass: \(result.output)")
    }

    /// An empty suffix is the same as none — an exported-but-blank variable
    /// still produces the installed app's identity, so it must not satisfy the
    /// guard.
    func testWorktreeBuildWithAnEmptySuffixFails() throws {
        let result = try runGuard(
            projectDir: "/Users/someone/Developer/jetlag/.ralph/worktrees/ralph-1/macos",
            bundleSuffix: "")

        XCTAssertNotEqual(result.status, 0)
    }

    /// A worktree build that carries a distinct identity is exactly what the
    /// guard asks for, so it proceeds.
    func testWorktreeBuildWithASuffixProceeds() throws {
        let result = try runGuard(
            projectDir: "/Users/someone/Developer/jetlag/.ralph/worktrees/ralph-1/macos",
            bundleSuffix: ".dev")

        XCTAssertEqual(result.status, 0, result.output)
    }

    /// The main checkout and the Xcode IDE build the real app under its real
    /// identity — the guard never asks them for anything.
    func testMainCheckoutBuildProceedsWithoutASuffix() throws {
        let result = try runGuard(
            projectDir: "/Users/someone/Developer/jetlag/macos",
            bundleSuffix: nil)

        XCTAssertEqual(result.status, 0, result.output)
    }
}
