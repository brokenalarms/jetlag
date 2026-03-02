import Foundation

struct DiffTableRow: Identifiable {
    let id = UUID()
    let file: String
    var tagAction: String?
    var tagsAdded: String?
    var originalTime: String?
    var correctedTime: String?
    var timestampSource: String?
    var timestampAction: String?
    var timezone: String?
    var correctionMode: String?
    var timeOffsetDisplay: String?
    var timestampError: String?
    var renamedTo: String?
    var dest: String?
    var organizeAction: String?
    var pipelineResult: String?

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
