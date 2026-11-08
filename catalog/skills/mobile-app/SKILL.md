---
name: mobile-app
description: Change Kotlin + Jetpack Compose and SwiftUI companion apps safely, keeping logic testable and verifying with the platform's test runner.
requires:
  tools: [Read, Edit, Bash]
  capabilities: [mobile-toolchain]
---
# Mobile companion apps

## Non-negotiables

- Logic lives in view models and plain Kotlin or Swift types with no UI-framework import,
  so it runs under JUnit or XCTest without an emulator or simulator.
- Bytes on the wire (BLE frames, provisioning payloads, WebSocket messages) are built from
  UTF-8 byte counts and explicit byte order, never from character counts or platform defaults.
- Tokens and credentials go only in the Keychain or EncryptedSharedPreferences; never in
  UserDefaults, SharedPreferences, logs or source.
- UI state is updated on the main thread from one source of truth (StateFlow or
  `@Published` / `@Observable`); views never hold business state.
- Permissions and Bluetooth state are checked before use and every failure path reaches
  the user as a message, not a silent return.

## Procedure for a change

1. Read the module's existing view model and model types before adding any; match the
   architecture already in place (MVVM in both apps).
2. Find the test command: `./gradlew test` with the Gradle wrapper for Android,
   `swift test` for a Swift package, `xcodebuild test` with the project's scheme for an
   Xcode project. Check that the wrapper or toolchain actually exists before relying on it.
   If `swift test` reports `no such module 'XCTest'`, the active developer directory is the
   Command Line Tools; rerun with `DEVELOPER_DIR` set to Xcode's Developer directory.
3. Make the smallest change that fixes the cause. Do not restyle neighbouring code and do
   not touch generated or resource files unless the change needs them.
4. Add or extend a unit test that fails before the change and passes after it.
5. Run the tests. If no toolchain can run them on this machine, say exactly which
   command failed or which tool is missing.

## Reporting

State what changed and why, the exact test command that ran, and its result. A change
whose tests did not run is reported as unverified, with the reason.
