plugins { id("com.android.application"); id("org.jetbrains.kotlin.android"); id("org.jetbrains.kotlin.plugin.compose") }

android {
    namespace = "com.apexbooks.accounting"
    compileSdk = 36
    testBuildType = providers.gradleProperty("apexTestBuildType").orElse("debug").get()
    defaultConfig {
        applicationId = "com.apexbooks.accounting"
        minSdk = 26
        targetSdk = 36
        versionCode = 9
        versionName = "1.4.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["keepSession"] = providers.gradleProperty("apexKeepQaSession").orElse("false").get()
    }
    signingConfigs {
        // Verification deliberately never reads release-signing environment or keys.
        val location = if (providers.gradleProperty("apexUnsignedReleaseVerification").orNull == "true") null else System.getenv("APEX_ANDROID_KEYSTORE")
        if (!location.isNullOrBlank()) {
            create("release") {
                storeFile = file(location)
                storePassword = System.getenv("APEX_ANDROID_STORE_PASSWORD")
                keyAlias = System.getenv("APEX_ANDROID_KEY_ALIAS") ?: "apex-books-release"
                keyPassword = System.getenv("APEX_ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        debug { applicationIdSuffix = ".debug"; resValue("string", "app_name", "Apex Books Dev");val qaOrigin=providers.gradleProperty("apexApiOrigin").orElse("http://10.0.2.2:8012").get();require(qaOrigin.matches(Regex("https?://[A-Za-z0-9.:-]+"))){"Use a plain QA server origin"};buildConfigField("String","API_ORIGIN","\"$qaOrigin\"") }
        release { buildConfigField("String","API_ORIGIN","\"https://api.apexbooks.in\"");isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro");testProguardFiles("proguard-test-rules.pro");if(providers.gradleProperty("apexTestBuildType").orNull=="release")proguardFiles("proguard-instrumented-host.pro");signingConfigs.findByName("release")?.let { signingConfig = it } }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    buildFeatures { compose = true; buildConfig = true }
    sourceSets["main"].assets.srcDir("../../shared")
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.10.01"))
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    androidTestImplementation("junit:junit:4.13.2")
    androidTestImplementation("com.google.errorprone:error_prone_annotations:2.42.0")
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
