Fixture: a cut-down shared-logic package from the iOS companion app (Swift package, XCTest, no UI).
Tests: `swift test` from this directory.
Known defect used by the mobile-engineer evals: `WiFiProvisioning.frame` writes the password length as a
character count, so a password with non-ASCII characters produces a frame the device cannot parse.
