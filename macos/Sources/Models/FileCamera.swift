import Foundation

/// The camera a file says shot it, as reported on `tag_result` only where it
/// differs from the profile's. The pipeline leaves the file's values in place;
/// the mismatch means the profile was likely picked for the wrong camera.
struct FileCamera: Equatable {
    let make: String?
    let model: String?

    init?(make: String?, model: String?) {
        guard make != nil || model != nil else { return nil }
        self.make = make
        self.model = model
    }

    var name: String {
        [make, model].compactMap { $0 }.joined(separator: " ")
    }
}
