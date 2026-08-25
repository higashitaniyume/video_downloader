import java.net.URL
import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "top.valency.videodownloader"
    compileSdk = 36

    val localProperties = Properties()
    val localPropertiesFile = rootProject.file("local.properties")
    if (localPropertiesFile.exists()) {
        localPropertiesFile.inputStream().use { localProperties.load(it) }
    }

    signingConfigs {
        create("release") {
            val storeFileProp = localProperties.getProperty("RELEASE_STORE_FILE")
            if (storeFileProp != null) {
                storeFile = file(storeFileProp)
                storePassword = localProperties.getProperty("RELEASE_STORE_PASSWORD")
                keyAlias = localProperties.getProperty("RELEASE_KEY_ALIAS")
                keyPassword = localProperties.getProperty("RELEASE_KEY_PASSWORD")
            }
        }
    }

    defaultConfig {
        applicationId = "top.valency.videodownloader"
        minSdk = 30
        targetSdk = 34
        versionCode = 5
        versionName = "1.2.1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }

        ndk {
            abiFilters.add("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (localProperties.getProperty("RELEASE_STORE_FILE") != null) {
                signingConfig = signingConfigs.getByName("release")
            }
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.11"
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            install("yt-dlp>=2025.1.26")
            install("aiohttp>=3.10.0")
            install("requests>=2.31.0")
            install("pillow>=10.0.0")
            install("pycryptodome>=3.20.0")
            install("pyyaml>=6.0")
        }
    }
}

tasks.register<Copy>("syncPythonFiles") {
    from(file("../../app"))
    into(file("src/main/python/app"))
    exclude("**/__pycache__/**")
    exclude("gui.py")
    exclude("settings_dialog.py")
    exclude("theme.py")
    exclude("web/**")
}

tasks.register("downloadFFmpeg") {
    val destDir = file("src/main/jniLibs/arm64-v8a")
    val destFile = File(destDir, "libffmpeg.so")
    
    inputs.property("url", "https://github.com/hzw1199/Android-FFmpeg-Prebuilt/raw/main/ffmpeg-9.0/bin/ffmpeg")
    outputs.file(destFile)
    
    doLast {
        if (!destFile.exists()) {
            destDir.mkdirs()
            println("Downloading FFmpeg for arm64-v8a...")
            val url = URL("https://github.com/hzw1199/Android-FFmpeg-Prebuilt/raw/main/ffmpeg-9.0/bin/ffmpeg")
            url.openStream().use { input ->
                destFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
            println("FFmpeg download complete.")
        }
    }
}

tasks.named("preBuild") {
    dependsOn("syncPythonFiles")
    dependsOn("downloadFFmpeg")
}

// Fix Gradle validation: declare dependency on syncPythonFiles for Chaquopy's merge tasks
tasks.configureEach {
    if (name.startsWith("merge") && name.endsWith("PythonSources")) {
        dependsOn("syncPythonFiles")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation(platform("androidx.compose:compose-bom:2024.02.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("io.coil-kt:coil-compose:2.6.0")
    
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.02.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
