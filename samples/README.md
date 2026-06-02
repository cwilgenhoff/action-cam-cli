# samples/ — local-only media (not committed)

Drop real footage and real Garmin GPX exports here for local, manual testing —
e.g. `samples/ride.gpx`, `samples/clips/`.

**Everything in this folder except this README is git-ignored on purpose:**
- real GPX files contain your actual GPS coordinates and timestamps (privacy), and
- footage is large.

Automated tests use small, anonymized, committed fixtures under `tests/fixtures/`
instead — never anything from here.
