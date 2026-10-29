import Foundation

/// A run that ended before its first file because the source held nothing the
/// profile matches, as the pipeline stated it in its `no_media_files` event.
struct EmptySource: Equatable {
    let source: String
    let extensions: [String]
}
