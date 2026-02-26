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
    var dest: String?
    var organizeAction: String?
    var pipelineResult: String?

    // Stage completion tracking (set by @@stage_complete events)
    var completedStages: Set<String> = []

    mutating func markStageComplete(_ stage: String) {
        completedStages.insert(stage)
    }
}
