import Foundation

/// The files the pipeline found shot on a camera other than the profile's, as its
/// `camera_mismatch` event reported them before processing anything.
struct CameraMismatch: Equatable {
    let files: [String]
    let expected: FileCamera?
    let foundMakes: [String]
    let foundModels: [String]

    var foundName: String {
        (foundMakes + foundModels).joined(separator: ", ")
    }
}
