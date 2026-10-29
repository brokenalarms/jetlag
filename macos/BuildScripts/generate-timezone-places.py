#!/usr/bin/env python3
"""
Generate macos/Sources/Resources/timezone-places.json — the place names the
timezone picker searches beyond the IANA identifier itself.

Usage (macOS only — the identifiers are the ones Foundation offers):
    python3 macos/BuildScripts/generate-timezone-places.py [cities15000.txt]

Without a path, downloads GeoNames' cities15000 dump (CC BY 4.0,
https://www.geonames.org). Each zone gets:
  - cities: places of at least MIN_POPULATION in that zone, largest first —
    an identifier names one city per zone, so Mumbai and Jaipur are otherwise
    unreachable behind Asia/Calcutta
  - countries: ISO 3166 codes from tzdb's zone.tab, localized by the app
  - aliases: other tzdb names for the same zone (Asia/Kolkata for
    Asia/Calcutta), since Foundation lists only one of them
"""
import io
import json
import os
import subprocess
import sys
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict

GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
MIN_POPULATION = 100_000
ZONEINFO = "/usr/share/zoneinfo"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "../Sources/Resources/timezone-places.json")

GEONAMES_NAME = 1
GEONAMES_POPULATION = 14
GEONAMES_ZONE = 17


def foundation_identifiers() -> list[str]:
    out = subprocess.run(
        ["swift", "-e", "import Foundation; TimeZone.knownTimeZoneIdentifiers.forEach { print($0) }"],
        check=True, capture_output=True, text=True,
    ).stdout
    return out.split()


def read_cities(path: str | None) -> list[str]:
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    with urllib.request.urlopen(GEONAMES_URL) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    return archive.read("cities15000.txt").decode("utf-8").splitlines()


def zone_files() -> dict[str, bytes]:
    files = {}
    for root, _, names in os.walk(ZONEINFO):
        for name in names:
            full = os.path.join(root, name)
            zone = os.path.relpath(full, ZONEINFO)
            if "/" not in zone or zone.startswith(("posix/", "right/", "Etc/")):
                continue
            with open(full, "rb") as f:
                data = f.read()
            if data.startswith(b"TZif"):
                files[zone] = data
    return files


def canonical_map(known: list[str], files: dict[str, bytes]) -> dict[str, str]:
    """Every tzdb name → the Foundation identifier with the same zone data."""
    by_data = {}
    for identifier in known:
        if identifier in files:
            by_data.setdefault(files[identifier], identifier)
    mapping = {identifier: identifier for identifier in known}
    for zone, data in files.items():
        if zone not in mapping and data in by_data:
            mapping[zone] = by_data[data]
    return mapping


def read_countries(canonical: dict[str, str]) -> dict[str, set[str]]:
    countries = defaultdict(set)
    with open(os.path.join(ZONEINFO, "zone.tab"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            code, _, zone = line.split("\t")[:3]
            identifier = canonical.get(zone.strip())
            if identifier:
                countries[identifier].add(code)
    return countries


def fold(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def city_part(zone: str) -> str:
    return zone.split("/")[-1].replace("_", " ")


def main() -> None:
    known = foundation_identifiers()
    files = zone_files()
    canonical = canonical_map(known, files)

    countries = read_countries(canonical)
    cities = defaultdict(list)
    for line in read_cities(sys.argv[1] if len(sys.argv) > 1 else None):
        fields = line.split("\t")
        identifier = canonical.get(fields[GEONAMES_ZONE])
        if identifier is None:
            continue
        population = int(fields[GEONAMES_POPULATION] or 0)
        if population >= MIN_POPULATION:
            cities[identifier].append((population, fields[GEONAMES_NAME]))

    aliases = defaultdict(set)
    for zone, identifier in canonical.items():
        if zone not in known and fold(city_part(zone)) != fold(city_part(identifier)):
            aliases[identifier].add(zone)

    places = {}
    for identifier in sorted(known):
        named = {fold(city_part(identifier))} | {fold(city_part(alias)) for alias in aliases[identifier]}
        names = []
        for _, name in sorted(cities[identifier], reverse=True):
            if fold(name) not in named:
                named.add(fold(name))
                names.append(name)
        entry = {
            "cities": names,
            "countries": sorted(countries[identifier]),
            "aliases": sorted(aliases[identifier]),
        }
        entry = {key: value for key, value in entry.items() if value}
        if entry:
            places[identifier] = entry

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"Wrote {len(places)} zones to {os.path.relpath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
