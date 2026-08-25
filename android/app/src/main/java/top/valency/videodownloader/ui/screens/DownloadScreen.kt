package top.valency.videodownloader.ui.screens

import android.content.Intent
import android.os.Build
import android.widget.Toast
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
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
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // App Title Header
            item {
                Spacer(modifier = Modifier.height(12.dp))
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Universal Downloader",
                        fontSize = 26.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = MaterialTheme.colorScheme.onBackground,
                        textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "支持 哔哩哔哩 / 抖音 / YouTube / 禁漫JM 等多平台音视频与漫画",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.primary,
                        textAlign = TextAlign.Center
                    )
                }
            }

            // Error Alert Banner
            item {
                AnimatedVisibility(
                    visible = parseError != null,
                    enter = fadeIn() + expandVertically(),
                    exit = fadeOut() + shrinkVertically()
                ) {
                    parseError?.let { errText ->
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.9f),
                            shape = RoundedCornerShape(16.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(14.dp),
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
                                        text = "解析提醒",
                                        fontWeight = FontWeight.Bold,
                                        color = MaterialTheme.colorScheme.onErrorContainer,
                                        fontSize = 14.sp
                                    )
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Text(
                                        text = errText,
                                        color = MaterialTheme.colorScheme.onErrorContainer,
                                        fontSize = 12.sp
                                    )
                                }
                                IconButton(
                                    onClick = { parseError = null },
                                    modifier = Modifier.size(24.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Close,
                                        contentDescription = "Dismiss",
                                        tint = MaterialTheme.colorScheme.onErrorContainer,
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // URL Parser Input Card
            item {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                    border = androidx.compose.foundation.BorderStroke(
                        1.dp,
                        MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f)
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        OutlinedTextField(
                            value = urlInput,
                            onValueChange = { urlInput = it },
                            modifier = Modifier.fillMaxWidth(),
                            placeholder = {
                                Text(
                                    "粘贴视频链接、漫画号 (如 jm123456) 或多行链接...",
                                    fontSize = 13.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                )
                            },
                            minLines = 2,
                            maxLines = 5,
                            shape = RoundedCornerShape(12.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)
                            )
                        )

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            FilledTonalButton(
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
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Icon(Icons.Default.ContentPaste, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("粘贴", fontSize = 13.sp)
                            }

                            OutlinedButton(
                                onClick = {
                                    urlInput = ""
                                    parseResults = emptyList()
                                    parseError = null
                                    selectedItems.clear()
                                },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Icon(Icons.Default.Clear, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(6.dp))
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
                                                    val author = res.get("author")?.toString() ?: ""
                                                    val desc = res.get("desc")?.toString() ?: ""
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
                                                            author = author,
                                                            desc = desc,
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
                                                    // 智能默认勾选：JM漫画默认仅选第一项（PDF全本），视频默认选首个主视频，图集默认全选
                                                    parsedList.forEach { card ->
                                                        if (card.platform.equals("jm", ignoreCase = true)) {
                                                            card.items.firstOrNull()?.let { selectedItems.add(it) }
                                                        } else {
                                                            val primaryVideos = card.items.filter { it.kind == "video" }
                                                            if (primaryVideos.isNotEmpty()) {
                                                                selectedItems.add(primaryVideos.first())
                                                            } else {
                                                                selectedItems.addAll(card.items)
                                                            }
                                                        }
                                                    }
                                                    if (errorsList.isNotEmpty()) {
                                                        parseError = "部分解析失败: ${errorsList.joinToString("; ")}"
                                                    }
                                                    delay(200)
                                                    downloaderListState.animateScrollToItem(index = 2)
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
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(46.dp),
                            enabled = !isParsing,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            if (isParsing) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp),
                                    strokeWidth = 2.dp,
                                    color = MaterialTheme.colorScheme.onPrimary
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("正在并发解析中...", fontSize = 14.sp, fontWeight = FontWeight.Bold)
                            } else {
                                Icon(Icons.Default.Bolt, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("一键解析", fontSize = 15.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }

            // Batch Action Bar when multiple results
            if (parseResults.size > 1) {
                item {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = "已解析 ${parseResults.size} 个作品",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                                Text(
                                    text = "共选择 ${selectedItems.size} 个下载项",
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }

                            Button(
                                onClick = {
                                    if (selectedItems.isEmpty()) {
                                        Toast.makeText(context, "请先勾选需要下载的项", Toast.LENGTH_SHORT).show()
                                        return@Button
                                    }
                                    var startedCount = 0
                                    parseResults.forEach { card ->
                                        val cardSelected = selectedItems.filter { it.parentUrl == card.url || card.items.contains(it) }
                                        if (cardSelected.isNotEmpty()) {
                                            triggerDownload(card.url, card.title, card.platform, cardSelected)
                                            startedCount++
                                        }
                                    }
                                    Toast.makeText(context, "已启动 $startedCount 个作品的后台下载", Toast.LENGTH_SHORT).show()
                                },
                                enabled = selectedItems.isNotEmpty(),
                                shape = RoundedCornerShape(10.dp),
                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)
                            ) {
                                Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("批量全部下载", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }

            // Render Parsed Result Cards
            items(
                items = parseResults,
                key = { it.id }
            ) { card ->
                ParsedMediaCard(
                    card = card,
                    selectedItems = selectedItems,
                    onToggleSelect = { item, isSelected ->
                        if (isSelected) {
                            if (!selectedItems.contains(item)) selectedItems.add(item)
                        } else {
                            selectedItems.remove(item)
                        }
                    },
                    onSelectOnly = { item ->
                        // 移除该卡片其他选中的项，仅保留当前项
                        val cardOtherItems = card.items.toSet()
                        selectedItems.removeAll { cardOtherItems.contains(it) }
                        selectedItems.add(item)
                    },
                    onDownloadCard = { cardItems ->
                        triggerDownload(card.url, card.title, card.platform, cardItems)
                        Toast.makeText(context, "已加入下载队列: ${card.title}", Toast.LENGTH_SHORT).show()
                    }
                )
            }

            item {
                Spacer(modifier = Modifier.height(80.dp))
            }
        }

        // Floating Action Download Manager Pill
        AnimatedVisibility(
            visible = activeDownloads.isNotEmpty(),
            enter = scaleIn() + fadeIn(),
            exit = scaleOut() + fadeOut(),
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(end = 16.dp, bottom = 16.dp)
        ) {
            Surface(
                onClick = { showDownloadSheet = true },
                shape = RoundedCornerShape(28.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
                shadowElevation = 8.dp,
                border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.3f))
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    if (runningCount > 0) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.5.dp,
                            color = MaterialTheme.colorScheme.primary
                        )
                    } else {
                        Icon(
                            imageVector = Icons.Default.CheckCircle,
                            contentDescription = null,
                            tint = Color(0xFF10B981),
                            modifier = Modifier.size(20.dp)
                        )
                    }
                    Text(
                        text = if (runningCount > 0) "正在下载 ($runningCount)" else "下载完成 ($totalCount)",
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }
        }

        // Modal Bottom Sheet Task Manager
        if (showDownloadSheet) {
            ModalBottomSheet(
                onDismissRequest = { showDownloadSheet = false },
                sheetState = sheetState,
                containerColor = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp)
                        .padding(bottom = 28.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
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
                                text = "共 $totalCount 个任务 · ${if (runningCount > 0) "$runningCount 个进行中" else "全部就绪"}",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            if (activeDownloads.values.any { it.isFinished || it.isFailed }) {
                                TextButton(
                                    onClick = { DownloadTracker.clearFinished() },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text("清空完成", fontSize = 12.sp)
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

                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
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
                                .heightIn(max = 500.dp),
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
fun ParsedMediaCard(
    card: ParseResultUi,
    selectedItems: List<MediaItemUi>,
    onToggleSelect: (MediaItemUi, Boolean) -> Unit,
    onSelectOnly: (MediaItemUi) -> Unit,
    onDownloadCard: (List<MediaItemUi>) -> Unit
) {
    val context = LocalContext.current
    var isChaptersExpanded by remember { mutableStateOf(false) }

    val isComic = card.platform.equals("jm", ignoreCase = true) || card.items.any { it.kind == "pdf" }
    val cardSelected = selectedItems.filter { it.parentUrl == card.url || card.items.contains(it) }

    // Platform Badge Theme Color
    val (platformBadgeBg, platformBadgeText) = when {
        card.platform.contains("jm", ignoreCase = true) -> Color(0xFF6366F1) to Color.White
        card.platform.contains("bilibili", ignoreCase = true) -> Color(0xFFFB7299) to Color.White
        card.platform.contains("douyin", ignoreCase = true) -> Color(0xFF1E293B) to Color(0xFF00F2FE)
        card.platform.contains("youtube", ignoreCase = true) -> Color(0xFFFF0000) to Color.White
        else -> MaterialTheme.colorScheme.primary to MaterialTheme.colorScheme.onPrimary
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header Tags & Platform
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = platformBadgeBg
                ) {
                    Text(
                        text = if (card.platform.equals("jm", ignoreCase = true)) "JM COMIC" else card.platform.uppercase(),
                        color = platformBadgeText,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.ExtraBold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }

                if (card.durationText.isNotEmpty()) {
                    Text(
                        text = card.durationText,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
            }

            // Title
            Text(
                text = card.title,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            // Author / Desc info
            if (card.author.isNotEmpty() || card.desc.isNotEmpty()) {
                Text(
                    text = listOfNotNull(
                        if (card.author.isNotEmpty()) "作者: ${card.author}" else null,
                        if (card.desc.isNotEmpty()) card.desc else null
                    ).joinToString(" | "),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            // Cover Image
            if (card.coverUrl.isNotEmpty()) {
                val coverRequest = ImageRequest.Builder(context)
                    .data(card.coverUrl)
                    .setHeader(
                        "Referer", when {
                            card.platform.contains("bilibili", ignoreCase = true) -> "https://www.bilibili.com"
                            card.platform.contains("douyin", ignoreCase = true) -> "https://www.douyin.com"
                            card.platform.contains("jm", ignoreCase = true) -> "https://18comic.vip"
                            else -> ""
                        }
                    )
                    .crossfade(true)
                    .build()

                AsyncImage(
                    model = coverRequest,
                    contentDescription = "Cover",
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp)
                        .clip(RoundedCornerShape(12.dp)),
                    contentScale = ContentScale.Crop
                )
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f))

            // ──────────────────── FORMAT SELECTION AREA ────────────────────
            if (isComic) {
                // COMIC FORMAT SELECTOR: Clean 3-mode segmented selection
                val pdfAllItem = card.items.find { it.formatId == "pdf:all" }
                val imgAllItem = card.items.find { it.formatId == "images:all" }
                val chapterItems = card.items.filter { it.formatId != "pdf:all" && it.formatId != "images:all" }

                Text(
                    text = "选择导出格式与章节:",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    if (pdfAllItem != null) {
                        val isSelected = selectedItems.contains(pdfAllItem)
                        FilterChip(
                            selected = isSelected,
                            onClick = {
                                onSelectOnly(pdfAllItem)
                                isChaptersExpanded = false
                            },
                            label = { Text("📄 全本 PDF", fontSize = 12.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(8.dp)
                        )
                    }

                    if (imgAllItem != null) {
                        val isSelected = selectedItems.contains(imgAllItem)
                        FilterChip(
                            selected = isSelected,
                            onClick = {
                                onSelectOnly(imgAllItem)
                                isChaptersExpanded = false
                            },
                            label = { Text("🖼️ 全本图片", fontSize = 12.sp, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(8.dp)
                        )
                    }
                }

                if (chapterItems.isNotEmpty()) {
                    OutlinedButton(
                        onClick = { isChaptersExpanded = !isChaptersExpanded },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "📑 自选章节 (${chapterItems.size / 2} 话)",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Icon(
                                imageVector = if (isChaptersExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                    }

                    AnimatedVisibility(
                        visible = isChaptersExpanded,
                        enter = expandVertically() + fadeIn(),
                        exit = shrinkVertically() + fadeOut()
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(
                                    MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                                    RoundedCornerShape(8.dp)
                                )
                                .padding(8.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                TextButton(
                                    onClick = {
                                        // 全选分章节 PDF
                                        val pdfChapters = chapterItems.filter { it.kind == "pdf" }
                                        pdfChapters.forEach { onToggleSelect(it, true) }
                                    },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                                ) {
                                    Text("全选 PDF 章节", fontSize = 11.sp)
                                }
                                TextButton(
                                    onClick = {
                                        chapterItems.forEach { onToggleSelect(it, false) }
                                    },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                                ) {
                                    Text("清空章节选择", fontSize = 11.sp)
                                }
                            }

                            chapterItems.forEach { item ->
                                val isChecked = selectedItems.contains(item)
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(6.dp))
                                        .clickable { onToggleSelect(item, !isChecked) }
                                        .padding(horizontal = 6.dp, vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.weight(1f)
                                    ) {
                                        Surface(
                                            shape = RoundedCornerShape(4.dp),
                                            color = if (item.kind == "pdf") MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer
                                        ) {
                                            Text(
                                                text = item.kind.uppercase(),
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold,
                                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                                            )
                                        }
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(
                                            text = item.name,
                                            fontSize = 12.sp,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                    }
                                    Checkbox(
                                        checked = isChecked,
                                        onCheckedChange = { onToggleSelect(item, it) },
                                        modifier = Modifier.size(24.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            } else {
                // VIDEO & GENERAL MEDIA FORMAT SELECTOR
                Text(
                    text = "下载档位/格式选择:",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface
                )

                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    card.items.forEach { item ->
                        val isChecked = selectedItems.contains(item)
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .clickable { onToggleSelect(item, !isChecked) },
                            color = if (isChecked) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f) else Color.Transparent,
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 8.dp, vertical = 6.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.weight(1f)
                                ) {
                                    val bgBadge = when (item.kind) {
                                        "video" -> MaterialTheme.colorScheme.primaryContainer
                                        "audio" -> MaterialTheme.colorScheme.tertiaryContainer
                                        else -> MaterialTheme.colorScheme.secondaryContainer
                                    }
                                    Surface(shape = RoundedCornerShape(4.dp), color = bgBadge) {
                                        Text(
                                            text = item.kind.uppercase(),
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Bold,
                                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                        )
                                    }
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = item.name,
                                        fontSize = 13.sp,
                                        color = MaterialTheme.colorScheme.onSurface,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                                Checkbox(
                                    checked = isChecked,
                                    onCheckedChange = { onToggleSelect(item, it) },
                                    modifier = Modifier.size(24.dp)
                                )
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Action Button
            Button(
                onClick = {
                    if (cardSelected.isEmpty()) {
                        Toast.makeText(context, "请先选择下载项", Toast.LENGTH_SHORT).show()
                        return@Button
                    }
                    onDownloadCard(cardSelected)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp),
                shape = RoundedCornerShape(10.dp),
                enabled = cardSelected.isNotEmpty()
            ) {
                Icon(Icons.Default.FileDownload, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = "立即下载 (${cardSelected.size} 项)",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold
                )
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
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
            border = androidx.compose.foundation.BorderStroke(
                1.dp,
                if (dl.isFailed) MaterialTheme.colorScheme.error.copy(alpha = 0.4f)
                else MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f)
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
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )

                    val pct = if (dl.totalBytes > 0) (dl.downloadedBytes * 100 / dl.totalBytes).toInt() else 0
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = when {
                                dl.isFailed -> MaterialTheme.colorScheme.errorContainer
                                dl.isFinished -> Color(0xFF10B981).copy(alpha = 0.15f)
                                else -> MaterialTheme.colorScheme.primaryContainer
                            }
                        ) {
                            Text(
                                text = when {
                                    dl.isFailed -> "失败"
                                    dl.isFinished -> "已完成"
                                    else -> "$pct%"
                                },
                                color = when {
                                    dl.isFailed -> MaterialTheme.colorScheme.error
                                    dl.isFinished -> Color(0xFF10B981)
                                    else -> MaterialTheme.colorScheme.primary
                                },
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }

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
                } else if (dl.isFinished) {
                    LinearProgressIndicator(
                        progress = { 1.0f },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp)),
                        color = Color(0xFF10B981),
                        trackColor = MaterialTheme.colorScheme.surfaceVariant
                    )

                    if (dl.filePaths.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
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
                                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                        FilledTonalButton(
                                            onClick = { openFile(context, filePath) },
                                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                            modifier = Modifier.height(28.dp),
                                            shape = RoundedCornerShape(6.dp)
                                        ) {
                                            Text("打开", fontSize = 11.sp)
                                        }
                                        OutlinedButton(
                                            onClick = { shareFile(context, filePath) },
                                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                            modifier = Modifier.height(28.dp),
                                            shape = RoundedCornerShape(6.dp)
                                        ) {
                                            Text("分享", fontSize = 11.sp)
                                        }
                                    }
                                }
                            }

                            TextButton(
                                onClick = { openFolder(context, dl.filePaths.first()) },
                                contentPadding = PaddingValues(horizontal = 0.dp),
                                modifier = Modifier
                                    .align(Alignment.Start)
                                    .height(28.dp)
                            ) {
                                Icon(Icons.Default.Folder, contentDescription = null, modifier = Modifier.size(14.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("打开所在文件夹", fontSize = 11.sp, color = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        }
    }
}
