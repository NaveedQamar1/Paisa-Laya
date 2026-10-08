plugins { id("com.android.application") }
android {
    namespace="com.easycopy.app"
    compileSdk=35
    defaultConfig { applicationId="com.easycopy.app"; minSdk=24; targetSdk=35; versionCode=2; versionName="2.1.0" }
    buildTypes { release { isMinifyEnabled=false; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"),"proguard-rules.pro") } }
    java { toolchain { languageVersion.set(JavaLanguageVersion.of(17)) } }
}
dependencies { implementation("androidx.core:core:1.15.0")
    implementation("org.opencv:opencv:4.10.0")
    implementation("com.google.mlkit:text-recognition:16.0.1") }