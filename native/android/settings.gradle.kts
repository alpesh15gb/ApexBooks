pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }
rootProject.name = "ApexBooks"
include(":app")

include(":backup-streaming")
project(":backup-streaming").projectDir = file("../shared/AndroidBackupStreaming")
