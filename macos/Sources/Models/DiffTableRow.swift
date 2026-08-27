import Foundation

struct DiffTableRow: Identifiable {
    let id = UUID()
    let file: String
    var tagAction: String?
    var tagsAdded: String?
    var originalTime: String?
    var correctedTime: String?
    var timestampSource: TimestampSource?
    var timestampAction: String?
    var timezone: String?
    var correctionMode: String?
    var timeOffsetDisplay: String?
    var timestampError: String?
    var renamedTo: String?
    var dest: String?
    var organizeAction: String?
    var organizeReason: String?
    var pipelineResult: String?
    var originalEpoch: Double?
    var correctedEpoch: Double?

    /// The write tags whose stored value differs from what the correction would
    /// give them. A row whose original and corrected times are the same string is
    /// only explicable by this list — it is what "Would fix" would actually write.
    var staleFields: [String] = []

    /// The file already carries a camera-set zone that the declared zone would
    /// relabel; applying needs the user's explicit confirmation.
    var requiresForceTimezone: Bool = false

    /// What the pipeline reported doing to this file, as tokens. The status the
    /// table shows is a function of these — never of whether `dest` is populated.
    var outcome: RowOutcome {
        RowOutcome(timestampAction: timestampAction, organizeAction: organizeAction)
    }

    /// Why the organize step left the file where it was, when it did.
    var skipReason: RowOutcome.SkipReason? {
        guard outcome.movement == .skipped else { return nil }
        return organizeReason.flatMap(RowOutcome.SkipReason.init(rawValue:))
    }

    /// A different file is already at this row's destination, so the move was
    /// refused. The table flags it because only these rows are what --overwrite
    /// would replace — an identical copy costs nothing to leave alone.
    var hasDestinationConflict: Bool {
        skipReason == .existsDiffers
    }

    /// The original timestamp as the table shows it. A UTC clock's stored digits
    /// carry no zone of their own, so the source decides how the value reads.
    var originalTimeDisplay: String? {
        guard let originalTime else { return nil }
        return timestampSource?.originalDisplay(originalTime) ?? originalTime
    }

    var completedStages: Set<String> = []

    mutating func markStageComplete(_ stage: String) {
        completedStages.insert(stage)
    }

    /// Stage order matching the pipeline execution sequence
    private static let stageOrder = ["ingest", "tag", "fix-timestamp", "output", "gyroflow"]

    /// Display label for the most recently completed stage
    var lastCompletedStageLabel: String? {
        for stage in Self.stageOrder.reversed() {
            if completedStages.contains(stage) {
                return Self.stageLabelMap[stage]
            }
        }
        return nil
    }

    private static let stageLabelMap: [String: String] = [
        "ingest": "Ingest",
        "tag": "Tag",
        "fix-timestamp": "Fix TS",
        "output": "Organize",
        "gyroflow": "Gyroflow",
    ]
}
