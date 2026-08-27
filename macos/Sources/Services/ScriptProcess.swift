import Foundation

/// A launched script and the process group it leads.
///
/// The pipeline is a tree — the script execs Python, which owns jetlag-metadata,
/// which owns `exiftool -stay_open`. Signalling the direct child alone leaves the
/// rest re-parented to launchd and still running, so the script is spawned as its
/// own process group leader and cancel signals the whole group.
final class ScriptProcess: @unchecked Sendable {
    /// How long the group is given to shut down on SIGTERM before it is killed.
    /// The pipeline's handler closes jetlag-metadata, which drains exiftool's
    /// pending command before sending it `-stay_open False`.
    static let terminationGracePeriod: TimeInterval = 5

    let processIdentifier: pid_t

    /// The group every process the script spawns belongs to. The script is spawned
    /// as the group's leader, so this is its own pid — recorded rather than looked
    /// up, because `getpgid` stops answering once the leader exits and the
    /// descendants that outlive it are exactly the ones cancel has to reach.
    var processGroupIdentifier: pid_t { processIdentifier }

    private let exited = NSCondition()
    private var hasExited = false

    init(processIdentifier: pid_t) {
        self.processIdentifier = processIdentifier
        guard processIdentifier > 0 else {
            // A spawn that never happened. Waiting on it must not block, and must
            // never reach waitpid, where a non-positive pid reaps unrelated children.
            hasExited = true
            return
        }
        // Reaping happens off a dedicated thread so the child never lingers as a
        // zombie when nobody calls waitUntilExit() — the cancel path does not.
        Thread.detachNewThread { [self] in
            var status: Int32 = 0
            while waitpid(processIdentifier, &status, 0) < 0 && errno == EINTR {}
            exited.lock()
            hasExited = true
            exited.broadcast()
            exited.unlock()
        }
    }

    func waitUntilExit() {
        exited.lock()
        while !hasExited { exited.wait() }
        exited.unlock()
    }

    /// Ask the whole process group to stop, then kill whatever is left.
    ///
    /// SIGTERM gives the pipeline's handler a chance to close jetlag-metadata and
    /// exiftool in order; anything still alive after the grace period is killed so
    /// a wedged child cannot outlive the run.
    func terminateGroup(gracePeriod: TimeInterval = ScriptProcess.terminationGracePeriod) {
        let group = processGroupIdentifier
        guard group > 0 else { return }
        kill(-group, SIGTERM)

        let deadline = Date().addingTimeInterval(gracePeriod)
        DispatchQueue.global().async { [self] in
            exited.lock()
            while !hasExited, Date() < deadline {
                exited.wait(until: deadline)
            }
            let stillRunning = !hasExited
            exited.unlock()
            if stillRunning || kill(-group, 0) == 0 {
                kill(-group, SIGKILL)
            }
        }
    }
}
