import Foundation

/// JSONL event types emitted by media-pipeline.sh on stdout.
enum PipelineEvent: Decodable {
    case pipelineFile(file: String, sourcePath: String?)
    case stageComplete(stage: String)
    case tagResult(file: String, action: String, tagsAdded: [String],
                   exifMake: String, exifModel: String, fileCamera: FileCamera?)
    case timestampResult(file: String, action: String,
                         originalTime: String?, correctedTime: String?,
                         source: String?, timezone: String?,
                         correctionMode: String?,
                         timeOffsetSeconds: Int?,
                         timeOffsetDisplay: String?,
                         error: String?,
                         reason: String?,
                         originalEpoch: Double?,
                         correctedEpoch: Double?,
                         requiresForceTimezone: Bool,
                         staleFields: [String],
                         staleFileTimes: [String])
    case renameResult(file: String, renamedTo: String)
    case organizeResult(file: String, action: String, dest: String, reason: String?)
    /// The table has no gyroflow column, so nothing of the event is read; its
    /// stage shows through `stage_complete`.
    case gyroflowResult
    case pipelineResult(file: String, result: String)
    case pipelineSummary(PipelineSummary)
    case batchCheck(BatchCheck)
    case noMediaFiles(EmptySource)
    case pipelineError(message: String)

    private enum CodingKeys: String, CodingKey {
        case event, file, stage, action
        case sourcePath = "source_path"
        case tagsAdded = "tags_added"
        case exifMake = "exif_make"
        case exifModel = "exif_model"
        case fileMake = "file_make"
        case fileModel = "file_model"
        case originalTime = "original_time"
        case correctedTime = "corrected_time"
        case source, timezone
        case correctionMode = "correction_mode"
        case timeOffsetSeconds = "time_offset_seconds"
        case timeOffsetDisplay = "time_offset_display"
        case originalEpoch = "original_epoch"
        case correctedEpoch = "corrected_epoch"
        case requiresForceTimezone = "requires_force_timezone"
        case staleFields = "stale_fields"
        case staleFileTimes = "stale_file_times"
        case renamedTo = "renamed_to"
        case dest, reason
        case error, result, message
        case check, files, groups, refused, extensions
        case assentFlag = "assent_flag"
        case processed, succeeded, changed, failed, mode
        case failedFiles = "failed_files"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let event = try container.decode(String.self, forKey: .event)

        switch event {
        case "pipeline_file":
            self = .pipelineFile(
                file: try container.decode(String.self, forKey: .file),
                sourcePath: try container.decodeIfPresent(String.self, forKey: .sourcePath))
        case "stage_complete":
            self = .stageComplete(
                stage: try container.decode(String.self, forKey: .stage))
        case "tag_result":
            self = .tagResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                tagsAdded: try container.decode([String].self, forKey: .tagsAdded),
                exifMake: try container.decode(String.self, forKey: .exifMake),
                exifModel: try container.decode(String.self, forKey: .exifModel),
                fileCamera: FileCamera(
                    make: try container.decodeIfPresent(String.self, forKey: .fileMake),
                    model: try container.decodeIfPresent(String.self, forKey: .fileModel)))
        case "timestamp_result":
            self = .timestampResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                originalTime: try container.decodeIfPresent(String.self, forKey: .originalTime),
                correctedTime: try container.decodeIfPresent(String.self, forKey: .correctedTime),
                source: try container.decodeIfPresent(String.self, forKey: .source),
                timezone: try container.decodeIfPresent(String.self, forKey: .timezone),
                correctionMode: try container.decodeIfPresent(String.self, forKey: .correctionMode),
                timeOffsetSeconds: try container.decodeIfPresent(Int.self, forKey: .timeOffsetSeconds),
                timeOffsetDisplay: try container.decodeIfPresent(String.self, forKey: .timeOffsetDisplay),
                error: try container.decodeIfPresent(String.self, forKey: .error),
                reason: try container.decodeIfPresent(String.self, forKey: .reason),
                originalEpoch: try container.decodeIfPresent(Double.self, forKey: .originalEpoch),
                correctedEpoch: try container.decodeIfPresent(Double.self, forKey: .correctedEpoch),
                requiresForceTimezone: try container.decodeIfPresent(Bool.self, forKey: .requiresForceTimezone) ?? false,
                staleFields: try container.decodeIfPresent([String].self, forKey: .staleFields) ?? [],
                staleFileTimes: try container.decodeIfPresent([String].self, forKey: .staleFileTimes) ?? [])
        case "rename_result":
            self = .renameResult(
                file: try container.decode(String.self, forKey: .file),
                renamedTo: try container.decode(String.self, forKey: .renamedTo))
        case "organize_result":
            self = .organizeResult(
                file: try container.decode(String.self, forKey: .file),
                action: try container.decode(String.self, forKey: .action),
                dest: try container.decode(String.self, forKey: .dest),
                reason: try container.decodeIfPresent(String.self, forKey: .reason))
        case "gyroflow_result":
            self = .gyroflowResult
        case "pipeline_result":
            self = .pipelineResult(
                file: try container.decode(String.self, forKey: .file),
                result: try container.decode(String.self, forKey: .result))
        case "pipeline_summary":
            let modeToken = try container.decode(String.self, forKey: .mode)
            guard let mode = PipelineSummary.Mode(rawValue: modeToken) else {
                throw DecodingError.dataCorruptedError(
                    forKey: .mode, in: container,
                    debugDescription: "Unknown pipeline_summary mode: \(modeToken)")
            }
            self = .pipelineSummary(PipelineSummary(
                processed: try container.decode(Int.self, forKey: .processed),
                succeeded: try container.decode(Int.self, forKey: .succeeded),
                changed: try container.decode(Int.self, forKey: .changed),
                failed: try container.decode(Int.self, forKey: .failed),
                failedFiles: try container.decode([String].self, forKey: .failedFiles),
                mode: mode))
        case "batch_check":
            let kindToken = try container.decode(String.self, forKey: .check)
            guard let kind = BatchCheck.Kind(rawValue: kindToken) else {
                throw DecodingError.dataCorruptedError(
                    forKey: .check, in: container,
                    debugDescription: "Unknown batch_check check: \(kindToken)")
            }
            self = .batchCheck(BatchCheck(
                kind: kind,
                files: try container.decode([String].self, forKey: .files),
                groups: try container.decodeIfPresent([String: [String]].self, forKey: .groups) ?? [:],
                assentFlag: try container.decodeIfPresent(String.self, forKey: .assentFlag),
                refused: try container.decode(Bool.self, forKey: .refused)))
        case "no_media_files":
            self = .noMediaFiles(EmptySource(
                source: try container.decode(String.self, forKey: .source),
                extensions: try container.decode([String].self, forKey: .extensions)))
        case "pipeline_error":
            self = .pipelineError(
                message: try container.decode(String.self, forKey: .message))
        default:
            throw DecodingError.dataCorruptedError(
                forKey: .event, in: container,
                debugDescription: "Unknown event type: \(event)")
        }
    }
}
