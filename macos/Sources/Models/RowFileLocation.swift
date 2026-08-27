import Foundation

/// Where a row's file currently lives on disk: `dest` once organize has placed
/// it there, otherwise wherever the pipeline read it from, under `sourceDir`.
/// Never re-derives this from display state — `dest` is the same field the
/// table already uses to decide whether a file moved.
///
/// The pre-move path is a guess, not a certainty: the pipeline's
/// `pipeline_file` event only ever carries a basename (`file_path.name`), and
/// the source scan is recursive, so two same-named files in different
/// subdirectories of `sourceDir` would resolve to the same path here.
enum RowFileLocation {
    static func path(for row: DiffTableRow, sourceDir: String) -> String? {
        if let dest = row.dest {
            return dest
        }
        guard !sourceDir.isEmpty else { return nil }
        return (sourceDir as NSString).appendingPathComponent(row.file)
    }

    static func exists(
        for row: DiffTableRow, sourceDir: String, fileManager: FileManager = .default
    ) -> Bool {
        guard let path = path(for: row, sourceDir: sourceDir) else { return false }
        return fileManager.fileExists(atPath: path)
    }
}
