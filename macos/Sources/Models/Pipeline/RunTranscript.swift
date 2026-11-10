import Foundation

/// What a run's pipeline events say about its files: the rows the pipeline has
/// finished with, the file it is working on, and what it reported about the
/// whole batch.
///
/// A value folded one event at a time by `apply(_:)`. An event that asks
/// something of the app beyond the table — a conflict the user must answer, an
/// error to log — is handed back as a `Notice` for `AppState` to act on.
struct RunTranscript {
    /// The files the pipeline has finished with, in the order it reported them.
    var rows: [DiffTableRow] = []
    /// The file the pipeline is working on, shown live below the finished rows.
    private(set) var liveRow: DiffTableRow?
    /// What the run reported when it reached the end of the batch. A cancelled
    /// run never produces one: the pipeline is killed before it reports.
    private(set) var summary: PipelineSummary?
    /// Set when the run found nothing to process, so the inspector can say where
    /// it looked instead of showing the never-run placeholder.
    private(set) var emptySource: EmptySource?

    /// What a row the pipeline moved past without a verdict is left showing.
    static let unfinishedResult = "in_progress"

    /// An event about the run as a whole, for the app to act on.
    enum Notice {
        case timezoneConflict(kind: TimezoneConflictKind, providedTz: String?,
                              fileTimezones: [String: [String]])
        case organizeConflict(count: Int, files: [String])
        case protectedSources(files: [String])
        case cameraMismatch(CameraMismatch)
        case error(message: String)
    }

    /// All finished rows plus the file in progress, for the live table.
    var visibleRows: [DiffTableRow] {
        guard let liveRow else { return rows }
        return rows + [liveRow]
    }

    /// Fold one event in. Returns what the app has to act on, if anything.
    mutating func apply(_ event: PipelineEvent) -> Notice? {
        switch event {
        case .pipelineFile(let file, let sourcePath):
            if var row = liveRow {
                row.pipelineResult = row.pipelineResult ?? Self.unfinishedResult
                rows.append(row)
            }
            var started = DiffTableRow(file: file)
            started.sourcePath = sourcePath
            liveRow = started

        case .pipelineResult(_, let result):
            if var row = liveRow {
                row.pipelineResult = result
                rows.append(row)
                liveRow = nil
            }

        case .tagResult(_, let action, let tagsAdded, _, _, let fileCamera):
            liveRow?.fileCamera = fileCamera
            liveRow?.tagAction = action
            liveRow?.tagsAdded = tagsAdded.joined(separator: ", ")

        case .timestampResult(_, let action, let originalTime, let correctedTime,
                              let source, let timezone, let correctionMode,
                              _, let timeOffsetDisplay, let error,
                              let originalEpoch, let correctedEpoch,
                              let requiresForceTimezone, let staleFields, let staleFileTimes):
            liveRow?.timestampAction = action
            liveRow?.originalTime = originalTime
            liveRow?.correctedTime = correctedTime
            liveRow?.timestampSource = TimestampSource(token: source)
            liveRow?.timezone = timezone
            liveRow?.correctionMode = correctionMode
            liveRow?.timeOffsetDisplay = timeOffsetDisplay
            liveRow?.timestampError = error
            liveRow?.originalEpoch = originalEpoch
            liveRow?.correctedEpoch = correctedEpoch
            liveRow?.requiresForceTimezone = requiresForceTimezone
            liveRow?.staleFields = staleFields
            liveRow?.staleFileTimes = staleFileTimes

        case .renameResult(_, let renamedTo):
            liveRow?.renamedTo = renamedTo

        case .organizeResult(_, let action, let dest, let reason):
            liveRow?.organizeAction = action
            liveRow?.dest = dest
            liveRow?.organizeReason = reason

        case .gyroflowResult:
            break

        case .stageComplete(let stage):
            liveRow?.markStageComplete(stage)

        case .pipelineSummary(let reported):
            summary = reported

        case .noMediaFiles(let empty):
            emptySource = empty

        case .timezoneConflict(let kind, let providedTz, let fileTimezones):
            return .timezoneConflict(kind: kind, providedTz: providedTz, fileTimezones: fileTimezones)

        case .organizeConflict(let count, let files):
            return .organizeConflict(count: count, files: files)

        case .protectedSources(let files):
            return .protectedSources(files: files)

        case .cameraMismatch(let mismatch):
            return .cameraMismatch(mismatch)

        case .pipelineError(let message):
            return .error(message: message)
        }
        return nil
    }

    /// A cancelled run never finishes the file it was on, so its row is
    /// withdrawn rather than left parked on its last stage.
    mutating func dropLiveRow() {
        liveRow = nil
    }
}
