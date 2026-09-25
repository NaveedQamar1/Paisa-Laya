plugins {
    id("com.android.application")
}

android {
    // Google AuthorizationClient is used for private Google Drive app-data sync.

    namespace = "com.paisalaya.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.paisalaya.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 3
        versionName = "1.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}


dependencies {
    implementation("com.google.android.gms:play-services-auth:21.5.0")
}
