package top.valency.videodownloader.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chaquo.python.Kwarg
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var proxyUrl by remember { mutableStateOf("") }
    var qualitySelection by remember { mutableStateOf("auto") }
    var cookiesText by remember { mutableStateOf("") }

    // Load initial settings
    LaunchedEffect(Unit) {
        scope.launch(Dispatchers.IO) {
            try {
                val python = Python.getInstance()
                val os = python.getModule("os")
                os.get("environ")!!.callAttr("__setitem__", "ANDROID_DATA_DIR", context.filesDir.absolutePath)

                val configModule = python.getModule("app.config")
                val appConfigClass = configModule.get("AppConfig")!!
                val config = appConfigClass.callAttr("load")

                proxyUrl = config.get("proxy_url")?.toString() ?: ""
                qualitySelection = config.get("quality")?.toString() ?: "auto"
                val cookiesFile = config.get("ydl_cookies_file")?.toString() ?: ""

                if (cookiesFile.isNotEmpty()) {
                    val file = File(cookiesFile)
                    if (file.exists()) {
                        cookiesText = file.readText()
                    }
                }
            } catch (e: Exception) {
                // Ignore load error
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Settings & Proxy",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground
            )
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Proxy Input
                    Text(
                        text = "Proxy URL (e.g. http://192.168.31.100:7890)",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    OutlinedTextField(
                        value = proxyUrl,
                        onValueChange = { proxyUrl = it },
                        placeholder = { Text("http://...") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Cookies Text Input
                    Text(
                        text = "Cookies Text (Netscape cookies.txt format)",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    OutlinedTextField(
                        value = cookiesText,
                        onValueChange = { cookiesText = it },
                        placeholder = { Text("# Netscape HTTP Cookie File...") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(240.dp),
                        maxLines = 15
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Save Button
                    Button(
                        onClick = {
                            scope.launch(Dispatchers.IO) {
                                try {
                                    val python = Python.getInstance()
                                    val configModule = python.getModule("app.config")
                                    val appConfigClass = configModule.get("AppConfig")!!

                                    // Save cookies file if provided
                                    val cookiesFilePath = if (cookiesText.isNotBlank()) {
                                        val cookiesFile = File(context.filesDir, "cookies.txt")
                                        cookiesFile.writeText(cookiesText)
                                        cookiesFile.absolutePath
                                    } else {
                                        val cookiesFile = File(context.filesDir, "cookies.txt")
                                        if (cookiesFile.exists()) cookiesFile.delete()
                                        ""
                                    }

                                    val configInstance = appConfigClass.call(
                                        Kwarg("proxy_url", proxyUrl),
                                        Kwarg("quality", qualitySelection),
                                        Kwarg("ydl_cookies_from_browser", ""),
                                        Kwarg("ydl_cookies_file", cookiesFilePath)
                                    )
                                    configInstance.callAttr("save")

                                    withContext(Dispatchers.Main) {
                                        Toast.makeText(context, "Settings saved successfully", Toast.LENGTH_SHORT).show()
                                    }
                                } catch (e: Exception) {
                                    withContext(Dispatchers.Main) {
                                        Toast.makeText(context, "Failed to save settings: ${e.message}", Toast.LENGTH_LONG).show()
                                    }
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Save Settings", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}
