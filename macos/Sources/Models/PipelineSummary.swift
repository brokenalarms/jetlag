import Foundation

/// What a finished run reported about the whole batch, as the pipeline stated it
/// in its `pipeline_summary` event. print_summary writes the same counts to
/// stderr for the log; this is the data the completion popup reads, so nothing
/// in the app re-derives an outcome from that formatted text.
struct PipelineSummary: Equatable {
    /// Whether the run wrote the changes or only previewed them. The run says
    /// which it was — the app never infers it from its own settings, which can
    /// have been changed since the run started.
    enum Mode: String {
        case applied
        case dryRun = "dry_run"
    }

    let processed: Int
    let succeeded: Int
    let changed: Int
    let failed: Int
    let failedFiles: [String]
    let mode: Mode

    var unchanged: Int { succeeded - changed }

    /// The completion popup's text. A dry run that found files from another
    /// camera says so, since an apply of the same batch will stop to ask.
    func message(cameraMismatch: CameraMismatch?) -> String {
        var lines = [Strings.Workflow.runSummaryCounts(
            processed: processed, changed: changed, mode: mode)]
        lines.append(mode == .applied
                     ? Strings.Workflow.runSummaryApplied
                     : Strings.Workflow.runSummaryDryRun)
        if failed > 0 {
            lines.append(Strings.Workflow.runSummaryFailed(count: failed, files: failedFiles))
        }
        if mode == .dryRun, let mismatch = cameraMismatch {
            lines.append(Strings.Workflow.runSummaryCameraMismatch(
                count: mismatch.files.count,
                found: mismatch.foundName,
                expected: mismatch.expected?.name ?? ""))
        }
        return lines.joined(separator: "\n\n")
    }
}
