plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.sky.companion"
    compileSdk = 34
    defaultConfig {
        applicationId = "app.sky.companion"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "2.39.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("boolean", "LIVE_EXCHANGE_EXECUTION", "false")
        buildConfigField("int", "CLIENT_BUILD", "1")
        buildConfigField("String", "CLIENT_NAME", "\"sky-android\"")
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            // Signing config is injected on the trusted release host only.
        }
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
}
