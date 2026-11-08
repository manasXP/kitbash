plugins {
    kotlin("jvm") version "2.1.0"
}

repositories { mavenCentral() }

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}

tasks.test { useJUnitPlatform() }
