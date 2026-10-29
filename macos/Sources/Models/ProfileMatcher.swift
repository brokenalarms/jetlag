import Foundation

/// A camera and the kind of media it shot: what a profile is. One camera has
/// a photo profile and a video profile, never two of either. Case is ignored, as
/// the pipeline ignores it: cameras write SONY where a profile may say Sony.
struct CameraKind: Hashable {
    let camera: FileCamera
    let type: MediaType

    init?(camera: FileCamera?, type: MediaType) {
        guard let camera else { return nil }
        self.camera = camera
        self.type = type
    }

    init?(profile: MediaProfile) {
        self.init(camera: FileCamera(make: profile.exif?.make, model: profile.exif?.model),
                  type: profile.type ?? .video)
    }

    private var identity: [String] {
        [camera.make?.lowercased() ?? "", camera.model?.lowercased() ?? "", type.rawValue]
    }

    static func == (lhs: CameraKind, rhs: CameraKind) -> Bool { lhs.identity == rhs.identity }
    func hash(into hasher: inout Hasher) { hasher.combine(identity) }

    /// A profile's default name: its camera and kind of media.
    var defaultProfileName: String { "\(camera.name) \(type.label)" }
}

/// What the profiles' sources hold, measured against the profiles there are.
struct SourceContents: Equatable {
    struct Match: Equatable {
        let profileName: String
        let source: String
    }

    struct NewCamera: Equatable {
        let kind: CameraKind
        let source: String
        let extensions: [String]
    }

    /// Profiles whose camera's media is in a source, and the source it is in.
    var matched: [Match] = []
    /// Camera kinds found in a source that no profile has yet.
    var newCameras: [NewCamera] = []
    /// Sources holding media that records no camera at all.
    var cameralessSources: [String] = []

    var isEmpty: Bool { matched.isEmpty && newCameras.isEmpty && cameralessSources.isEmpty }
}

enum ProfileMatcher {

    /// Probes are keyed by the source folder they read.
    static func contents(of probes: [String: [ProbedCamera]], profiles: [String: MediaProfile]) -> SourceContents {
        var contents = SourceContents()
        for source in probes.keys.sorted() {
            for probe in probes[source]!.sorted(by: { $0.files > $1.files }) {
                guard let kind = CameraKind(camera: probe.camera, type: probe.type) else {
                    if !contents.cameralessSources.contains(source) {
                        contents.cameralessSources.append(source)
                    }
                    continue
                }
                if let name = profileName(for: kind, in: profiles) {
                    if !contents.matched.contains(where: { $0.profileName == name }) {
                        contents.matched.append(.init(profileName: name, source: source))
                    }
                } else if let index = contents.newCameras.firstIndex(where: { $0.kind == kind && $0.source == source }) {
                    let existing = contents.newCameras[index]
                    contents.newCameras[index] = .init(kind: kind, source: source,
                                                       extensions: (existing.extensions + [probe.fileExtension]).sorted())
                } else {
                    contents.newCameras.append(.init(kind: kind, source: source, extensions: [probe.fileExtension]))
                }
            }
        }
        return contents
    }

    static func profileName(for kind: CameraKind, in profiles: [String: MediaProfile]) -> String? {
        profiles.keys.sorted().first { CameraKind(profile: profiles[$0]!) == kind }
    }

    /// Profiles sharing a camera kind with another. Each kind is meant to have
    /// one profile; these predate that and are left for the user to resolve.
    static func duplicates(in profiles: [String: MediaProfile]) -> Set<String> {
        let byKind = Dictionary(grouping: profiles.keys) { CameraKind(profile: profiles[$0]!) }
        return Set(byKind.filter { $0.key != nil && $0.value.count > 1 }.values.joined())
    }
}
