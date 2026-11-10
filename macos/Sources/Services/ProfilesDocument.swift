import Foundation
import Yams

/// The profiles file is written as an edit of the file that was read, not as a
/// fresh encoding of the model. The model holds only the keys the app edits; a
/// fresh encoding would drop every other key the scripts read (a profile's
/// `folder_template`, the gyroflow preset's other settings) on the first save.
enum ProfilesDocument {
    /// How much of a mapping the model owns.
    indirect enum Shape {
        /// The model holds the value whole: what it writes replaces the file's.
        case value
        /// The model owns these keys of the mapping. One the model no longer
        /// writes is removed; any other key is the file's and is kept as it was.
        case fields([String: Shape])
    }

    static let profileShape: Shape = owning(MediaProfile.CodingKeys.self, nested: [
        .exif: owning(ExifConfig.CodingKeys.self),
        .gyroflowSettings: owning(StabilizationSettings.CodingKeys.self),
    ])

    /// `profiles` is merged entry by entry in `merge(_:into:)` — each profile
    /// over the block it was read from, which follows it through a rename — so
    /// at the top level it arrives already merged and is taken whole.
    static let documentShape: Shape = owning(ProfilesConfig.CodingKeys.self, nested: [
        .gyroflow: owning(GyroflowConfig.CodingKeys.self, nested: [
            .preset: owning(GyroflowPreset.CodingKeys.self, nested: [
                .stabilization: owning(StabilizationSettings.CodingKeys.self),
            ]),
        ]),
    ])

    private static func owning<Key: CodingKey & CaseIterable & Hashable>(
        _ keys: Key.Type, nested: [Key: Shape] = [:]
    ) -> Shape {
        .fields(Dictionary(uniqueKeysWithValues: keys.allCases.map {
            ($0.stringValue, nested[$0] ?? .value)
        }))
    }

    private static let profilesKey = ProfilesConfig.CodingKeys.profiles.stringValue

    /// Record on `config` the file it was decoded from — the whole document,
    /// and each profile's own block — so a later write can be laid over it.
    static func attach(_ document: Node?, to config: inout ProfilesConfig) {
        config.fileNode = document
        guard let entries = document.flatMap({ value(for: profilesKey, in: $0) })?.mapping else { return }
        for (key, block) in entries {
            guard let name = key.string, config.profiles[name] != nil else { continue }
            config.profiles[name]?.fileNode = block
        }
    }

    /// The file to write: `written`, the model freshly encoded, laid over the
    /// file `config` was read from.
    static func merge(_ written: Node, into config: ProfilesConfig) -> Node {
        var document = written
        if case .mapping(var top) = written,
           let index = top.firstIndex(where: { $0.key.string == profilesKey }),
           case .mapping(let entries) = top[index].value {
            top[index].value = .mapping(mergedProfiles(entries, config: config))
            document = .mapping(top)
        }
        return merge(document, over: config.fileNode, shape: documentShape)
    }

    /// Each profile laid over its own block, in the file's order, with new
    /// profiles after the ones the file already had.
    private static func mergedProfiles(_ entries: Node.Mapping, config: ProfilesConfig) -> Node.Mapping {
        let fileProfiles = config.fileNode.flatMap { value(for: profilesKey, in: $0) }?.mapping
        let fileOrder = fileProfiles?.compactMap { $0.key.string } ?? []
        func position(_ key: Node) -> Int {
            key.string.flatMap { fileOrder.firstIndex(of: $0) } ?? Int.max
        }
        let merged: [(Node, Node)] = entries.map { entry in
            let original = entry.key.string.flatMap { config.profiles[$0]?.fileNode }
            return (entry.key, merge(entry.value, over: original, shape: profileShape))
        }
        let ordered = merged.sorted { lhs, rhs in
            let (left, right) = (position(lhs.0), position(rhs.0))
            return left != right ? left < right : (lhs.0.string ?? "") < (rhs.0.string ?? "")
        }
        return Node.Mapping(ordered, entries.tag, entries.style)
    }

    /// `written` laid over `original`: the model's keys as the model has them,
    /// every other key as the file had it, in the file's order.
    static func merge(_ written: Node, over original: Node?, shape: Shape) -> Node {
        guard let original else { return written }
        if isUnchanged(written, from: original) { return original }
        guard case .fields(let owned) = shape,
              case .mapping(let writtenMapping) = written,
              case .mapping(let originalMapping) = original
        else { return written }

        var pairs: [(Node, Node)] = []
        var placed = Set<String>()
        for (key, value) in originalMapping {
            guard let name = key.string, let field = owned[name] else {
                pairs.append((key, value))
                continue
            }
            placed.insert(name)
            if let replacement = Self.value(for: name, in: writtenMapping) {
                pairs.append((key, merge(replacement, over: value, shape: field)))
            }
        }
        for (key, value) in writtenMapping where !placed.contains(key.string ?? "") {
            pairs.append((key, value))
        }
        return .mapping(Node.Mapping(pairs, originalMapping.tag, originalMapping.style))
    }

    /// Whether the model wrote back what the file holds. Yams writes a float
    /// in scientific notation (`1.05e+2`), so a float the file spells `105.0`
    /// is compared by value, and the file's spelling is what stays.
    private static func isUnchanged(_ written: Node, from original: Node) -> Bool {
        if written == original { return true }
        guard written.tag == Tag(.float),
              let writtenValue = written.float,
              let originalValue = original.float
        else { return false }
        return writtenValue == originalValue
    }

    private static func value(for name: String, in node: Node) -> Node? {
        node.mapping.flatMap { value(for: name, in: $0) }
    }

    private static func value(for name: String, in mapping: Node.Mapping) -> Node? {
        mapping.first { $0.key.string == name }?.value
    }
}
