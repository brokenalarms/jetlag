import Foundation

struct TimezoneOption: Identifiable, Equatable {
    let id: String
    let region: String
    let city: String
    let path: String
    let offset: String
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
            offset: formatOffset(tz.secondsFromGMT())
        )
    }

    static func offset(_ identifier: String) -> String? {
        option(identifier)?.offset
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
