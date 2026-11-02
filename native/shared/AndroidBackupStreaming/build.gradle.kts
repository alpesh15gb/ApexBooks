plugins { java }
if (rootProject == project) { repositories { mavenCentral() } }
java { sourceCompatibility = JavaVersion.VERSION_1_8; targetCompatibility = JavaVersion.VERSION_1_8 }
sourceSets { main { java.setSrcDirs(listOf("src")) }; test { java.setSrcDirs(listOf("../../tests/AndroidBackupStreaming")) } }
dependencies {
    implementation("org.bouncycastle:bcprov-jdk18on:1.86")
    implementation("com.fasterxml.jackson.core:jackson-core:2.21.8")
}
dependencyLocking { lockAllConfigurations() }
tasks.compileTestJava { options.release.set(17) }
tasks.register<JavaExec>("verifyBackupStreaming") {
    dependsOn(tasks.testClasses)
    doFirst { copy { from("../../tests/backup-fixtures"); into(layout.buildDirectory.dir("synthetic-fixtures")) } }
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("StreamingBackupTest")
    maxHeapSize = "64m"
    args(layout.buildDirectory.dir("synthetic-fixtures").get().asFile.absolutePath)
    providers.gradleProperty("largeMiB").orNull?.let { args(it) }
}
