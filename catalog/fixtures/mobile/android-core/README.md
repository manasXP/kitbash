Fixture: the pairing module of the Android companion app, Kotlin with JUnit 5 tests and no UI.
There is no Gradle wrapper here and no gradle or kotlinc on PATH; a Gradle distribution cached under ~/.gradle
plus Java 21 can run the tests (the first mobile-engineer eval run found and used it, 2 Nov 2026). The eval
accepts either a real run or a plain statement that the tests could not run; it rejects a claimed pass without output.
Known defect: `ProvisioningFrame.build` writes string lengths as character counts instead of UTF-8 byte counts.
