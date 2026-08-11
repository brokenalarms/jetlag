import Foundation

struct TimezoneOption: Identifiable, Equatable {
    let id: String
    let region: String
    let city: String
    let path: String
    let offsets: [String]

    /// Both offsets for a zone that observes DST — which one applies is decided
    /// per file, against the date it was shot.
    var offsetLabel: String { offsets.joined(separator: "/") }
}

enum TimezoneCatalog {
    static let all: [TimezoneOption] = TimeZone.knownTimeZoneIdentifiers.sorted().compactMap(option)

    static func option(_ identifier: String) -> TimezoneOption? {
        guard let tz = TimeZone(identifier: identifier) else { return nil }
        let components = identifier.components(separatedBy: "/")
        let names = components.dropFirst().map { $0.replacingOccurrences(of: "_", with: " ") }
        return TimezoneOption(
            id: identifier,
            region: components.first ?? identifier,
            city: names.last ?? identifier,
            path: names.isEmpty ? identifier : names.joined(separator: " / "),
            offsets: offsets(of: tz)
        )
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
