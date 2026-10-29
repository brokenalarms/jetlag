import XCTest
@testable import Jetlag

/// The timezone picker must find a zone by the place someone was actually in,
/// not only the one city its IANA identifier happens to name — India's single
/// zone is Asia/Calcutta, so Mumbai, Jaipur, "India" and the current name
/// Kolkata all have to reach it.
final class TimezoneCatalogTests: XCTestCase {

    private func match(_ query: String, in identifier: String) -> TimezoneMatch? {
        TimezoneCatalog.option(identifier)?.match(query)
    }

    func testCityOutsideTheIdentifierFindsItsZoneAndNamesThePlace() {
        XCTAssertEqual(match("mumbai", in: "Asia/Calcutta"), TimezoneMatch(place: "Mumbai"))
        XCTAssertEqual(match("Jaipur", in: "Asia/Calcutta"), TimezoneMatch(place: "Jaipur"))
    }

    func testCountryFindsItsZone() {
        XCTAssertEqual(match("india", in: "Asia/Calcutta")?.place, "India")
    }

    /// Foundation lists only the older tzdb name, so the current one is an alias.
    func testCurrentTzdbNameFindsTheListedOldOne() {
        XCTAssertEqual(match("Kolkata", in: "Asia/Calcutta"), TimezoneMatch(place: "Kolkata"))
        XCTAssertEqual(match("saigon", in: "Asia/Ho_Chi_Minh"), TimezoneMatch(place: "Saigon"))
    }

    /// Foundation maps IST to Asia/Kolkata, which it does not list itself.
    func testAbbreviationFindsTheZoneThroughItsAlias() {
        XCTAssertEqual(match("IST", in: "Asia/Calcutta"), TimezoneMatch(place: nil))
    }

    func testIdentifierMatchNeedsNoPlaceLabel() {
        XCTAssertEqual(match("calcutta", in: "Asia/Calcutta"), TimezoneMatch(place: nil))
    }

    func testAccentsAreIgnoredEitherWay() {
        XCTAssertEqual(match("Córdoba", in: "America/Argentina/Cordoba"), TimezoneMatch(place: nil))
        XCTAssertNotNil(match("zurich", in: "Europe/Zurich"))
    }

    func testUnrelatedPlaceDoesNotMatch() {
        XCTAssertNil(match("mumbai", in: "Asia/Karachi"))
    }
}
