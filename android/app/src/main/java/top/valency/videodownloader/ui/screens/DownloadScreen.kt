package top.valency.videodownloader.ui.screens

import android.content.Intent
import android.os.Build
import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Download
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
import top.valency.videodownloader.DownloadProgress
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var urlInput by remember { mutableStateOf("") }
    var isParsing by remember { mutableStateOf(false) }
    var parseResults by remember { mutableStateOf<List<ParseResultUi>>(emptyList()) }
    var parseError by remember { mutableStateOf<String?>(null) }
    val selectedItems = remember { mutableStateListOf<MediaItemUi>() }
    
    val activeDownloads by DownloadTracker.progress.collectAsState()
    val downloaderListState = rememberLazyListState()

    var showDownloadSheet by remember { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    fun triggerDownload(url: String, title: String, platform: String, itemsToDownload: List<MediaItemUi>) {
        if (itemsToDownload.isEmpty()) return
        val intent = Intent(context, DownloadService::class.java).apply {
            putExtra("url", url)
            putExtra("title", title)
            putExtra("platform", platform)
            putStringArrayListExtra("format_ids", ArrayList(itemsToDownload.map { it.formatId }))
            putStringArrayListExtra("names", ArrayList(itemsToDownload.map { it.name }))
            putStringArrayListExtra("kinds", ArrayList(itemsToDownload.map { it.kind }))
            putStringArrayListExtra("direct_urls", ArrayList(itemsToDownload.map { it.urls.joinToString("\t") }))
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent)
        } else {
            context.startService(intent)
        }
    }

    val runningCount = activeDownloads.values.count { !it.isFinished && !it.isFailed }
    val totalCount = activeDownloads.size

    Box(modifier = Modifier.fillMaxSize()) {
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
                Spacer(modifier = Modifier.height(4.dp))
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
                            text = "支持单条或多行链接批量解析",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        OutlinedTextField(
                            value = urlInput,
                            onValueChange = { urlInput = it },
                            modifier = Modifier.fillMaxWidth(),
                            placeholder = { Text("粘贴视频/漫画链接（支持 jm123456、网页链接、多行批量）...", fontSize = 13.sp) },
                            maxLines = 5,
                            shape = RoundedCornerShape(8.dp)
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Button(
                                onClick = {
                                    val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                                    val clipData = clipboard.primaryClip
                                    if (clipData != null && clipData.itemCount > 0) {
                                        val text = clipData.getItemAt(0).text?.toString() ?: ""
                                        if (text.isNotBlank()) {
                                            urlInput = text
                                            Toast.makeText(context, "已粘贴剪贴板内容", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                                    contentColor = MaterialTheme.colorScheme.onSecondaryContainer
                                )
                            ) {
                                Text("粘贴剪贴板", fontSize = 13.sp)
                            }

                            OutlinedButton(
                                onClick = {
                                    urlInput = ""
                                    parseResults = emptyList()
                                    parseError = null
                                    selectedItems.clear()
                                },
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("清空", fontSize = 13.sp)
                            }
                        }

                        Button(
                            onClick = {
                                if (urlInput.isBlank()) {
                                    Toast.makeText(context, "请先输入或粘贴链接", Toast.LENGTH_SHORT).show()
                                    return@Button
                                }
                                isParsing = true
                                parseResults = emptyList()
                                parseError = null
                                selectedItems.clear()
                                
                                scope.launch {
                                    delay(100)
                                    downloaderListState.animateScrollToItem(index = 2)
                                }

                                scope.launch(Dispatchers.IO) {
                                    try {
                                        val python = Python.getInstance()
                                        
                                        val os = python.getModule("os")
                                        os.get("environ")!!.callAttr("__setitem__", "ANDROID_DATA_DIR", context.filesDir.absolutePath)
                                        
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
                                            val parsedList = mutableListOf<ParseResultUi>()
                                            val errorsList = mutableListOf<String>()

                                            for (res in resultsList) {
                                                val error = res!!.get("error")
                                                if (error != null) {
                                                    errorsList.add(error.toString())
                                                } else {
                                                    val title = res.get("title")?.toString() ?: "（无标题）"
                                                    val platform = res.get("platform")?.toString() ?: "media"
                                                    val durationText = res.get("duration_text")?.toString() ?: ""
                                                    val resUrl = res.get("url")?.toString() ?: urlInput
                                                    
                                                    val itemsList = res.get("items")?.asList() ?: emptyList()
                                                    val itemsMapped = itemsList.map { itemPy ->
                                                        val urlsPy = itemPy!!.get("urls")?.asList() ?: emptyList()
                                                        MediaItemUi(
                                                            parentUrl = resUrl,
                                                            index = itemPy.get("index")!!.toInt(),
                                                            kind = itemPy.get("kind")!!.toString(),
                                                            name = itemPy.get("name")!!.toString(),
                                                            formatId = itemPy.get("format_id")!!.toString(),
                                                            urls = urlsPy.map { it.toString() }
                                                        )
                                                    }
                                                    
                                                    val coverUrlsPy = res.get("cover_urls")?.asList() ?: emptyList()
                                                    var coverUrl = if (coverUrlsPy.isNotEmpty()) coverUrlsPy[0]!!.toString() else ""
                                                    if (coverUrl.startsWith("http://")) {
                                                        coverUrl = coverUrl.replaceFirst("http://", "https://")
                                                    }

                                                    parsedList.add(
                                                        ParseResultUi(
                                                            url = resUrl,
                                                            platform = platform,
                                                            title = title,
                                                            durationText = durationText,
                                                            items = itemsMapped,
                                                            coverUrl = coverUrl
                                                        )
                                                    )
                                                }
                                            }

                                            if (parsedList.isNotEmpty()) {
                                                withContext(Dispatchers.Main) {
                                                    parseResults = parsedList
                                                    // 默认全选每张卡片的第一个主要视频或图集全部图片
                                                    parsedList.forEach { card ->
                                                        val primaryVideos = card.items.filter { it.kind == "video" }
                                                        if (primaryVideos.isNotEmpty()) {
                                                            selectedItems.add(primaryVideos.first())
                                                        } else {
                                                            selectedItems.addAll(card.items)
                                                        }
                                                    }
                                                    if (errorsList.isNotEmpty()) {
                                                        parseError = "部分解析失败: ${errorsList.joinToString("; ")}"
                                                    }
                                                    delay(200)
                                                    downloaderListState.animateScrollToItem(index = 3)
                                                }
                                            } else if (errorsList.isNotEmpty()) {
                                                withContext(Dispatchers.Main) {
                                                    parseError = errorsList.joinToString("\n")
                                                }
                                            }
                                        } else {
                                            withContext(Dispatchers.Main) {
                                                parseError = "未在输入中提取到任何有效链接"
                                            }
                                        }
                                    } catch (e: Exception) {
                                        withContext(Dispatchers.Main) {
                                            parseError = "解析失败: ${e.message}"
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
                                Text("正在解析中...")
                            } else {
                                Text("开始解析", fontWeight = FontWeight.Bold)
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
                                text = "正在努力并发解析链接，请稍候...",
                                fontWeight = FontWeight.Medium,
                                fontSize = 14.sp
                            )
                        }
                    }
                }
            }

            // Batch Download Action Toolbar (when multiple results parsed)
            if (parseResults.isNotEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = "已解析 ${parseResults.size} 个作品",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = "已选 ${selectedItems.size} 个下载项",
                                    fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }

                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                FilledTonalButton(
                                    onClick = {
                                        val allItems = parseResults.flatMap { it.items }
                                        if (selectedItems.size == allItems.size) {
                                            selectedItems.clear()
                                        } else {
                                            selectedItems.clear()
                                            selectedItems.addAll(allItems)
                                        }
                                    },
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp)
                                ) {
                                    val allItems = parseResults.flatMap { it.items }
                                    Text(if (selectedItems.size == allItems.size) "全不选" else "全选", fontSize = 12.sp)
                                }

                                Button(
                                    onClick = {
                                        if (selectedItems.isEmpty()) {
                                            Toast.makeText(context, "请先勾选需要下载的项", Toast.LENGTH_SHORT).show()
                                            return@Button
                                        }
                                        // 针对每个解析卡片分别启动后台下载服务
                                        var startedCount = 0
                                        parseResults.forEach { card ->
                                            val cardSelected = selectedItems.filter { it.parentUrl == card.url || card.items.contains(it) }
                                            if (cardSelected.isNotEmpty()) {
                                                triggerDownload(card.url, card.title, card.platform, cardSelected)
                                                startedCount++
                                            }
                                        }
                                        Toast.makeText(context, "已启动 $startedCount 个任务的后台下载", Toast.LENGTH_SHORT).show()
                                    },
                                    enabled = selectedItems.isNotEmpty(),
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                                ) {
                                    Text("一键下载全部", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            }

            // Render each Parsed Result Card
            items(
                items = parseResults,
                key = { it.id }
            ) { result ->
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
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                        
                        if (result.coverUrl.isNotEmpty()) {
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
                                contentDescription = "Cover Preview",
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(160.dp)
                                    .clip(RoundedCornerShape(8.dp)),
                                contentScale = ContentScale.Crop
                            )
                        }

                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

                        Text(
                            text = "选择要下载的档位/图片:",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )

                        // Render available formats in this card
                        result.items.forEach { item ->
                            val isChecked = selectedItems.contains(item)
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(
                                        if (isChecked) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f) else Color.Transparent,
                                        RoundedCornerShape(8.dp)
                                    )
                                    .padding(vertical = 4.dp, horizontal = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.weight(1f)
                                ) {
                                    val bgBadgeColor = when (item.kind) {
                                        "video" -> MaterialTheme.colorScheme.primaryContainer
                                        "image" -> MaterialTheme.colorScheme.secondaryContainer
                                        else -> MaterialTheme.colorScheme.tertiaryContainer
                                    }
                                    val onBadgeColor = when (item.kind) {
                                        "video" -> MaterialTheme.colorScheme.onPrimaryContainer
                                        "image" -> MaterialTheme.colorScheme.onSecondaryContainer
                                        else -> MaterialTheme.colorScheme.onTertiaryContainer
                                    }
                                    
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
                                        fontSize = 13.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
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

                        Spacer(modifier = Modifier.height(2.dp))

                        val cardSelectedItems = selectedItems.filter { it.parentUrl == result.url || result.items.contains(it) }
                        Button(
                            onClick = {
                                if (cardSelectedItems.isEmpty()) {
                                    Toast.makeText(context, "请先勾选该作品的下载档位", Toast.LENGTH_SHORT).show()
                                    return@Button
                                }
                                triggerDownload(result.url, result.title, result.platform, cardSelectedItems)
                                Toast.makeText(context, "已开始下载: ${result.title}", Toast.LENGTH_SHORT).show()
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = cardSelectedItems.isNotEmpty()
                        ) {
                            Text("下载当前作品 (${cardSelectedItems.size})", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            // Bottom space so content is not obscured by FAB
            item {
                Spacer(modifier = Modifier.height(72.dp))
            }
        }

        // Floating Action Button at bottom right when downloads exist
        AnimatedVisibility(
            visible = activeDownloads.isNotEmpty(),
            enter = scaleIn() + fadeIn(),
            exit = scaleOut() + fadeOut(),
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(end = 8.dp, bottom = 12.dp)
        ) {
            ExtendedFloatingActionButton(
                onClick = { showDownloadSheet = true },
                icon = {
                    BadgedBox(
                        badge = {
                            if (runningCount > 0) {
                                Badge(
                                    containerColor = MaterialTheme.colorScheme.error,
                                    contentColor = MaterialTheme.colorScheme.onError
                                ) {
                                    Text("$runningCount")
                                }
                            }
                        }
                    ) {
                        Icon(
                            imageVector = Icons.Default.Download,
                            contentDescription = "下载列表"
                        )
                    }
                },
                text = {
                    Text(
                        if (runningCount > 0) "下载中 ($runningCount)" else "下载列表 ($totalCount)",
                        fontWeight = FontWeight.SemiBold
                    )
                },
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                elevation = FloatingActionButtonDefaults.elevation(6.dp)
            )
        }

        // Modal Bottom Sheet showing active and completed downloads
        if (showDownloadSheet) {
            ModalBottomSheet(
                onDismissRequest = { showDownloadSheet = false },
                sheetState = sheetState,
                containerColor = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                        .padding(bottom = 24.dp)
                ) {
                    // Sheet Header
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "下载任务管理",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            Text(
                                text = "共 $totalCount 个任务${if (runningCount > 0) " · $runningCount 个正在进行" else " · 全部完成"}",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            if (activeDownloads.values.any { it.isFinished || it.isFailed }) {
                                TextButton(
                                    onClick = { DownloadTracker.clearFinished() },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text("清除已完成", fontSize = 12.sp)
                                }
                            }
                            IconButton(
                                onClick = { showDownloadSheet = false },
                                modifier = Modifier.size(32.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "关闭",
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }

                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    Spacer(modifier = Modifier.height(12.dp))

                    if (activeDownloads.isEmpty()) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(160.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "暂无下载任务",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 14.sp
                            )
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(max = 480.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            items(
                                items = activeDownloads.values.toList().reversed(),
                                key = { it.label }
                            ) { dl ->
                                DownloadItemCard(
                                    dl = dl,
                                    onDelete = { DownloadTracker.remove(dl.label) }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun DownloadItemCard(
    dl: DownloadProgress,
    onDelete: () -> Unit
) {
    val context = LocalContext.current
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
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
            )
        ) {
            Column(
                modifier = Modifier.padding(14.dp),
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
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    
                    val pct = if (dl.totalBytes > 0) (dl.downloadedBytes * 100 / dl.totalBytes).toInt() else 0
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Text(
                            text = if (dl.isFinished) {
                                if (dl.isFailed) "失败" else "已完成"
                            } else "$pct%",
                            color = if (dl.isFailed) MaterialTheme.colorScheme.error else if (dl.isFinished) Color(0xFF22C55E) else MaterialTheme.colorScheme.primary,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold
                        )
                        IconButton(
                            onClick = onDelete,
                            modifier = Modifier.size(24.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Close,
                                contentDescription = "移除任务",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                                modifier = Modifier.size(16.dp)
                            )
                        }
                    }
                }

                if (!dl.isFinished && dl.totalBytes > 0) {
                    LinearProgressIndicator(
                        progress = { dl.downloadedBytes.toFloat() / dl.totalBytes.toFloat() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
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
                        maxLines = 4,
                        overflow = TextOverflow.Ellipsis
                    )
                } else {
                    LinearProgressIndicator(
                        progress = { 1.0f },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp)),
                        color = Color(0xFF22C55E),
                        trackColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                    
                    if (dl.filePaths.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(2.dp))
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
                                Text("打开文件所在目录", fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        }
    }
}
