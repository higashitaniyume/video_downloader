package top.valency.videodownloader.ui.screens

import android.content.Intent
import android.os.Build
import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.chaquo.python.Kwarg
import com.chaquo.python.Python
import top.valency.videodownloader.DownloadService
import top.valency.videodownloader.DownloadTracker
import top.valency.videodownloader.models.MediaItemUi
import top.valency.videodownloader.models.ParseResultUi
import top.valency.videodownloader.utils.openFile
import top.valency.videodownloader.utils.openFolder
import top.valency.videodownloader.utils.shareFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@Composable
fun DownloadScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var urlInput by remember { mutableStateOf("") }
    var isParsing by remember { mutableStateOf(false) }
    var parseResult by remember { mutableStateOf<ParseResultUi?>(null) }
    var parseError by remember { mutableStateOf<String?>(null) }
    val selectedItems = remember { mutableStateListOf<MediaItemUi>() }
    
    val activeDownloads by DownloadTracker.progress.collectAsState()
    val downloaderListState = rememberLazyListState()

    LazyColumn(
        state = downloaderListState,
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // App Title Header
        item {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Video Downloader",
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "提示：下载的文件保存在“内部存储/Download/VideoDownloader”目录。",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(8.dp))
        }

        // Persistent Parser Error Card
        item {
            AnimatedVisibility(
                visible = parseError != null,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                parseError?.let { errText ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.Top
                        ) {
                            Icon(
                                imageVector = Icons.Default.Warning,
                                contentDescription = "Error",
                                tint = MaterialTheme.colorScheme.error,
                                modifier = Modifier.padding(top = 2.dp)
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = "解析出错 (Parse Error)",
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                    fontSize = 14.sp
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = errText,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                    fontSize = 13.sp
                                )
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                            IconButton(
                                onClick = { parseError = null },
                                modifier = Modifier.size(24.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "Dismiss",
                                    tint = MaterialTheme.colorScheme.onErrorContainer
                                )
                            }
                        }
                    }
                }
            }
        }

        // URL Parser Input Section
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "Paste Video URL",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    OutlinedTextField(
                        value = urlInput,
                        onValueChange = { urlInput = it },
                        placeholder = { Text("https://www.youtube.com/watch?...") },
                        modifier = Modifier.fillMaxWidth(),
                        maxLines = 3
                    )
                    
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(
                            onClick = {
                                try {
                                    val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val clip = clipboard.primaryClip
                                    if (clip != null && clip.itemCount > 0) {
                                        urlInput = clip.getItemAt(0).text?.toString() ?: ""
                                    } else {
                                        Toast.makeText(context, "剪贴板为空", Toast.LENGTH_SHORT).show()
                                    }
                                } catch (e: Exception) {
                                    Toast.makeText(context, "无法从剪贴板读取数据", Toast.LENGTH_SHORT).show()
                                }
                            },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Text("从剪贴板粘贴", fontSize = 13.sp)
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        TextButton(
                            onClick = { urlInput = "" },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Text("清空", fontSize = 13.sp)
                        }
                    }

                    Button(
                        onClick = {
                            if (urlInput.isBlank()) {
                                Toast.makeText(context, "Please paste a URL first", Toast.LENGTH_SHORT).show()
                                return@Button
                            }
                            isParsing = true
                            parseResult = null
                            parseError = null
                            selectedItems.clear()
                            
                            // Scroll to loader item when starting parse
                            scope.launch {
                                delay(100)
                                downloaderListState.animateScrollToItem(index = 2) // Index of parsing card
                            }

                            scope.launch(Dispatchers.IO) {
                                try {
                                    val python = Python.getInstance()
                                    
                                    // Configure android data dir
                                    val os = python.getModule("os")
                                    os.get("environ")!!.callAttr("__setitem__", "ANDROID_DATA_DIR", context.filesDir.absolutePath)
                                    
                                    // Load configuration to pass to engine
                                    val configModule = python.getModule("app.config")
                                    val appConfigClass = configModule.get("AppConfig")!!
                                    val config = appConfigClass.callAttr("load")
                                    
                                    val proxy = config.get("proxy_url")?.toString() ?: ""
                                    val quality = config.get("quality")?.toString() ?: "auto"
                                    val cookiesFile = config.get("ydl_cookies_file")?.toString() ?: ""
                                    
                                    val engineModule = python.getModule("app.engine")
                                    val parseEngineClass = engineModule.get("ParseEngine")!!
                                    val parseEngine = parseEngineClass.call(
                                        Kwarg("proxy", proxy),
                                        Kwarg("quality", quality),
                                        Kwarg("ydl_cookies_file", cookiesFile)
                                    )
                                    
                                    val resultsPy = parseEngine!!.callAttr("parse_text_sync", urlInput)
                                    val resultsList = resultsPy!!.asList()
                                    
                                    if (resultsList.isNotEmpty()) {
                                        val res = resultsList[0]
                                        val error = res!!.get("error")
                                        if (error != null) {
                                            withContext(Dispatchers.Main) {
                                                parseError = error.toString()
                                            }
                                        } else {
                                            val title = res!!.get("title")!!.toString()
                                            val platform = res!!.get("platform")!!.toString()
                                            val durationText = res!!.get("duration_text")!!.toString()
                                            
                                            val itemsList = res!!.get("items")!!.asList()
                                            val itemsMapped = itemsList!!.map { itemPy ->
                                                MediaItemUi(
                                                    index = itemPy!!.get("index")!!.toInt(),
                                                    kind = itemPy!!.get("kind")!!.toString(),
                                                    name = itemPy!!.get("name")!!.toString(),
                                                    formatId = itemPy!!.get("format_id")!!.toString()
                                                )
                                            }
                                            
                                            val coverUrlsPy = res!!.get("cover_urls")?.asList() ?: emptyList()
                                            var coverUrl = if (coverUrlsPy.isNotEmpty()) coverUrlsPy[0]!!.toString() else ""
                                            if (coverUrl.startsWith("http://")) {
                                                coverUrl = coverUrl.replaceFirst("http://", "https://")
                                            }

                                            parseResult = ParseResultUi(
                                                url = urlInput,
                                                platform = platform,
                                                title = title,
                                                durationText = durationText,
                                                items = itemsMapped,
                                                coverUrl = coverUrl
                                            )

                                            // Auto scroll to results section
                                            withContext(Dispatchers.Main) {
                                                delay(200)
                                                downloaderListState.animateScrollToItem(index = 4) // Index of results card
                                            }
                                        }
                                    } else {
                                        withContext(Dispatchers.Main) {
                                            parseError = "No URL found in input"
                                        }
                                    }
                                } catch (e: Exception) {
                                    withContext(Dispatchers.Main) {
                                        parseError = "Parse failed: ${e.message}"
                                    }
                                } finally {
                                    isParsing = false
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isParsing
                    ) {
                        if (isParsing) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Parsing...")
                        } else {
                            Text("Parse Link", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        // Parsing Dynamic Loading Card
        item {
            AnimatedVisibility(
                visible = isParsing,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            color = MaterialTheme.colorScheme.primary,
                            strokeWidth = 2.5.dp
                        )
                        Spacer(modifier = Modifier.width(16.dp))
                        Text(
                            text = "正在努力解析链接，请稍候...",
                            fontWeight = FontWeight.Medium,
                            fontSize = 14.sp
                        )
                    }
                }
            }
        }

        // Results Section
        item {
            AnimatedVisibility(
                visible = parseResult != null,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                parseResult?.let { result ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = result.platform.uppercase(),
                                    color = MaterialTheme.colorScheme.secondary,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier
                                        .background(MaterialTheme.colorScheme.secondaryContainer, RoundedCornerShape(4.dp))
                                        .padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                                if (result.durationText.isNotEmpty()) {
                                    Text(
                                        text = result.durationText,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 12.sp
                                    )
                                }
                            }
                            
                            Text(
                                text = result.title,
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            
                            if (result.coverUrl.isNotEmpty()) {
                                Spacer(modifier = Modifier.height(6.dp))
                                val coverRequest = ImageRequest.Builder(context)
                                    .data(result.coverUrl)
                                    .setHeader("Referer", when {
                                        result.platform.contains("bilibili", ignoreCase = true) || result.url.contains("bilibili", ignoreCase = true) -> "https://www.bilibili.com"
                                        result.platform.contains("douyin", ignoreCase = true) || result.url.contains("douyin", ignoreCase = true) -> "https://www.douyin.com"
                                        else -> ""
                                    })
                                    .crossfade(true)
                                    .build()

                                AsyncImage(
                                    model = coverRequest,
                                    contentDescription = "Video Cover Preview",
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(180.dp)
                                        .clip(RoundedCornerShape(8.dp)),
                                    contentScale = ContentScale.Crop
                                )
                            }

                            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

                            Text(
                                text = "Select Formats to Download:",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium
                            )

                            // Render available formats
                            result.items.forEach { item ->
                                val isChecked = selectedItems.contains(item)
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(
                                            if (isChecked) MaterialTheme.colorScheme.primaryContainer else Color.Transparent,
                                            RoundedCornerShape(8.dp)
                                        )
                                        .padding(vertical = 4.dp, horizontal = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        val bgBadgeColor = if (item.kind == "video") MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.tertiaryContainer
                                        val onBadgeColor = if (item.kind == "video") MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onTertiaryContainer
                                        
                                        Text(
                                            text = item.kind.uppercase(),
                                            color = onBadgeColor,
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Bold,
                                            modifier = Modifier
                                                .background(bgBadgeColor, RoundedCornerShape(4.dp))
                                                .padding(horizontal = 4.dp, vertical = 1.dp)
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            text = item.name,
                                            color = MaterialTheme.colorScheme.onSurface,
                                            fontSize = 14.sp
                                        )
                                    }
                                    Checkbox(
                                        checked = isChecked,
                                        onCheckedChange = { checked ->
                                            if (checked) {
                                                selectedItems.add(item)
                                            } else {
                                                selectedItems.remove(item)
                                            }
                                        }
                                    )
                                }
                            }

                            Spacer(modifier = Modifier.height(4.dp))

                            Button(
                                onClick = {
                                    if (selectedItems.isEmpty()) {
                                        Toast.makeText(context, "Select at least one format", Toast.LENGTH_SHORT).show()
                                        return@Button
                                    }

                                    // Trigger Foreground Service
                                    val intent = Intent(context, DownloadService::class.java).apply {
                                        putExtra("url", result.url)
                                        putExtra("title", result.title)
                                        putExtra("platform", result.platform)
                                        putStringArrayListExtra("format_ids", ArrayList(selectedItems.map { it.formatId }))
                                        putStringArrayListExtra("names", ArrayList(selectedItems.map { it.name }))
                                        putStringArrayListExtra("kinds", ArrayList(selectedItems.map { it.kind }))
                                    }
                                    
                                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                        context.startForegroundService(intent)
                                    } else {
                                        context.startService(intent)
                                    }

                                    Toast.makeText(context, "Download started in background", Toast.LENGTH_SHORT).show()
                                },
                                modifier = Modifier.fillMaxWidth(),
                                enabled = selectedItems.isNotEmpty()
                            ) {
                                Text("Download Selected (${selectedItems.size})", fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }

        // Active Downloads progress section
        if (activeDownloads.isNotEmpty()) {
            item {
                Text(
                    text = "下载队列 (Active Downloads)",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onBackground,
                    modifier = Modifier.padding(horizontal = 4.dp)
                )
            }
        }

        items(
            items = activeDownloads.values.toList().reversed(),
            key = { it.label }
        ) { dl ->
            val visibleState = remember { MutableTransitionState(false) }.apply {
                targetState = true
            }
            
            AnimatedVisibility(
                visibleState = visibleState,
                enter = fadeIn() + expandVertically(),
                exit = fadeOut() + shrinkVertically()
            ) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = dl.label,
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 14.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            val pct = if (dl.totalBytes > 0) (dl.downloadedBytes * 100 / dl.totalBytes).toInt() else 0
                            Text(
                                text = if (dl.isFinished) {
                                    if (dl.isFailed) "Failed" else "Complete"
                                } else "$pct%",
                                color = if (dl.isFailed) MaterialTheme.colorScheme.error else if (dl.isFinished) Color(0xFF22C55E) else MaterialTheme.colorScheme.primary,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }

                        if (!dl.isFinished && dl.totalBytes > 0) {
                            LinearProgressIndicator(
                                progress = { dl.downloadedBytes.toFloat() / dl.totalBytes.toFloat() },
                                modifier = Modifier.fillMaxWidth(),
                                color = MaterialTheme.colorScheme.primary,
                                trackColor = MaterialTheme.colorScheme.surfaceVariant
                            )
                            Text(
                                text = "${dl.downloadedBytes / (1024 * 1024)}MB / ${dl.totalBytes / (1024 * 1024)}MB",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        } else if (dl.isFailed && dl.errorMsg != null) {
                            Text(
                                text = dl.errorMsg,
                                color = MaterialTheme.colorScheme.error,
                                fontSize = 12.sp,
                                maxLines = 5,
                                overflow = TextOverflow.Ellipsis
                            )
                        } else {
                            LinearProgressIndicator(
                                progress = { 1.0f },
                                modifier = Modifier.fillMaxWidth(),
                                color = Color(0xFF22C55E),
                                trackColor = MaterialTheme.colorScheme.surfaceVariant
                            )
                            
                            if (dl.filePaths.isNotEmpty()) {
                                Spacer(modifier = Modifier.height(4.dp))
                                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    dl.filePaths.forEach { filePath ->
                                        val fileName = File(filePath).name
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = fileName,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                fontSize = 12.sp,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis,
                                                modifier = Modifier.weight(1f)
                                            )
                                            Row {
                                                TextButton(
                                                    onClick = { openFile(context, filePath) },
                                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                                                    modifier = Modifier.height(28.dp)
                                                ) {
                                                    Text("打开", fontSize = 12.sp)
                                                }
                                                Spacer(modifier = Modifier.width(4.dp))
                                                TextButton(
                                                    onClick = { shareFile(context, filePath) },
                                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                                                    modifier = Modifier.height(28.dp)
                                                ) {
                                                    Text("分享", fontSize = 12.sp)
                                                }
                                            }
                                        }
                                    }
                                    
                                    TextButton(
                                        onClick = { openFolder(context, dl.filePaths.first()) },
                                        contentPadding = PaddingValues(horizontal = 0.dp),
                                        modifier = Modifier.align(Alignment.Start).height(28.dp)
                                    ) {
                                        Text("打开文件夹所在位置", fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
