import Foundation

struct TimezoneOption: Identifiable, Equatable {
    let id: String
    let region: String
    let city: String
    let path: String
    let offsets: [String]
    /// Names that reach this zone without appearing in its identifier: other
    /// cities in it, other tzdb names for it, its countries and its zone name.
    let places: [String]
    let abbreviations: [String]

    /// Both offsets for a zone that observes DST — which one applies is decided
    /// per file, against the date it was shot.
    var offsetLabel: String { offsets.joined(separator: "/") }

    func match(_ query: String) -> TimezoneMatch? {
        if path.containsFolded(query) || region.containsFolded(query)
            || offsets.contains(where: { $0.contains(query) })
            || abbreviations.contains(where: { $0.caseInsensitiveCompare(query) == .orderedSame }) {
            return TimezoneMatch(place: nil)
        }
        return places.first { $0.containsFolded(query) }.map(TimezoneMatch.init)
    }
}

struct TimezoneMatch: Equatable {
    /// The place the search matched, when the zone's own name didn't.
    let place: String?
}

private struct TimezonePlaces: Decodable {
    let cities: [String]?
    let countries: [String]?
    let aliases: [String]?
}

enum TimezoneCatalog {
    static let all: [TimezoneOption] = TimeZone.knownTimeZoneIdentifiers.sorted().compactMap(option)

    private static let places: [String: TimezonePlaces] = {
        guard let url = Bundle.main.url(forResource: "timezone-places", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return [:] }
        return (try? JSONDecoder().decode([String: TimezonePlaces].self, from: data)) ?? [:]
    }()

    private static let abbreviations: [String: [String]] = {
        let aliasTargets = places.flatMap { identifier, entry in
            (entry.aliases ?? []).map { ($0, identifier) }
        }
        let canonical = Dictionary(aliasTargets, uniquingKeysWith: { first, _ in first })
        return Dictionary(
            grouping: TimeZone.abbreviationDictionary,
            by: { canonical[$0.value] ?? $0.value }
        ).mapValues { $0.map(\.key).sorted() }
    }()

    static func option(_ identifier: String) -> TimezoneOption? {
        guard let tz = TimeZone(identifier: identifier) else { return nil }
        let components = identifier.components(separatedBy: "/")
        let names = components.dropFirst().map { $0.replacingOccurrences(of: "_", with: " ") }
        return TimezoneOption(
            id: identifier,
            region: components.first ?? identifier,
            city: names.last ?? identifier,
            path: names.isEmpty ? identifier : names.joined(separator: " / "),
            offsets: offsets(of: tz),
            places: placeNames(of: identifier, tz: tz),
            abbreviations: abbreviations[identifier] ?? []
        )
    }

    private static func placeNames(of identifier: String, tz: TimeZone) -> [String] {
        let entry = places[identifier]
        let aliases = (entry?.aliases ?? []).compactMap { $0.components(separatedBy: "/").last }
            .map { $0.replacingOccurrences(of: "_", with: " ") }
        let countries = (entry?.countries ?? []).compactMap { Locale.current.localizedString(forRegionCode: $0) }
        let zoneName = tz.localizedName(for: .generic, locale: .current)
        return aliases + (entry?.cities ?? []) + countries + [zoneName].compactMap { $0 }
    }

    /// Standard offset first, then the daylight offset when the zone observes one.
    private static func offsets(of tz: TimeZone) -> [String] {
        let now = Date()
        let current = formatOffset(tz.secondsFromGMT(for: now))
        guard let transition = tz.nextDaylightSavingTimeTransition(after: now) else {
            return [current]
        }
        let other = formatOffset(tz.secondsFromGMT(for: transition.addingTimeInterval(1)))
        guard other != current else { return [current] }
        return [current, other].sorted()
    }

    private static func formatOffset(_ seconds: Int) -> String {
        let magnitude = abs(seconds)
        return String(
            format: "%@%02d%02d",
            seconds >= 0 ? "+" : "-",
            magnitude / 3600,
            (magnitude % 3600) / 60
        )
    }
}

private extension String {
    func containsFolded(_ query: String) -> Bool {
        range(of: query, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
}
