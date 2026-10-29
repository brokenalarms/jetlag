import Foundation

/// A camera as files record it: the Make and Model a file carries, either of
/// which may be missing. Reported by the pipeline where a file differs from its
/// profile, and by probe-camera for what shot a card.
struct FileCamera: Equatable {
    let make: String?
    let model: String?

    init?(make: String?, model: String?) {
        let make = make.flatMap { $0.isEmpty ? nil : $0 }
        let model = model.flatMap { $0.isEmpty ? nil : $0 }
        guard make != nil || model != nil else { return nil }
        self.make = make
        self.model = model
    }

    var name: String {
        [make, model].compactMap { $0 }.joined(separator: " ")
    }
}
