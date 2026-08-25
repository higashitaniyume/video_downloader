package top.valency.videodownloader

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.chaquo.python.Kwarg
import com.chaquo.python.Python
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import top.valency.videodownloader.utils.saveFileToMediaStore

data class DownloadProgress(
    val label: String,
    val downloadedBytes: Long,
    val totalBytes: Long,
    val isFinished: Boolean = false,
    val isFailed: Boolean = false,
    val errorMsg: String? = null,
    val filePaths: List<String> = emptyList()
)

object DownloadTracker {
    private val _progress = MutableStateFlow<Map<String, DownloadProgress>>(emptyMap())
    val progress = _progress.asStateFlow()

    fun updateProgress(label: String, update: DownloadProgress) {
        val current = _progress.value.toMutableMap()
        current[label] = update
        _progress.value = current
    }

    fun remove(label: String) {
        val current = _progress.value.toMutableMap()
        current.remove(label)
        _progress.value = current
    }

    fun clearFinished() {
        val current = _progress.value.toMutableMap()
        val filtered = current.filterValues { !it.isFinished && !it.isFailed }
        _progress.value = filtered
    }

    fun clear() {
        _progress.value = emptyMap()
    }
}

class DownloadService : Service() {

    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    
    private val CHANNEL_ID = "download_channel"
    private val NOTIFICATION_ID = 101

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val url = intent?.getStringExtra("url") ?: return START_NOT_STICKY
        val title = intent?.getStringExtra("title") ?: "Video"
        val platform = intent?.getStringExtra("platform") ?: "ydl"
        val formatIds = intent?.getStringArrayListExtra("format_ids") ?: arrayListOf()
        val names = intent?.getStringArrayListExtra("names") ?: arrayListOf()
        val kinds = intent?.getStringArrayListExtra("kinds") ?: arrayListOf()
        val directUrls = intent?.getStringArrayListExtra("direct_urls") ?: arrayListOf()

        // Start service as foreground immediately
        val notification = createNotification("Starting download for: $title", 0, 100)
        startForeground(NOTIFICATION_ID, notification)

        serviceScope.launch {
            try {
                runDownload(url, title, platform, formatIds, names, kinds, directUrls)
            } finally {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }

        return START_NOT_STICKY
    }

    private fun runDownload(
        url: String,
        title: String,
        platform: String,
        formatIds: List<String>,
        names: List<String>,
        kinds: List<String>,
        directUrls: List<String>
    ) {
        val python = Python.getInstance()
        
        // 1. Resolve storage paths
        // We save to standard internal cache directory first
        val downloadFolder = File(cacheDir, "VideoTemp").apply { mkdirs() }
        
        // 2. Set environment variables
        val os = python.getModule("os")
        os.get("environ")!!.callAttr("__setitem__", "ANDROID_DATA_DIR", filesDir.absolutePath)
        
        val ffmpegPath = File(applicationInfo.nativeLibraryDir, "libffmpeg.so").absolutePath
        os.get("environ")!!.callAttr("__setitem__", "FFMPEG_BINARY_PATH", ffmpegPath)

        // Load config
        val configModule = python.getModule("app.config")
        val appConfigClass = configModule.get("AppConfig")!!
        val config = appConfigClass.callAttr("load")
        
        val proxy = config.get("proxy_url")?.toString() ?: ""
        val cookiesFile = config.get("ydl_cookies_file")?.toString() ?: ""

        // 3. Prepare Python Downloader parameters
        val ydlModule = python.getModule("app.ydl")
        val engineModule = python.getModule("app.engine")

        val parseResultClass = engineModule.get("ParseResult")!!
        val mediaItemClass = engineModule.get("MediaItem")!!

        // Construct ParseResult
        val mediaItemsPyList = python.getBuiltins().get("list")!!.call()
        for (i in formatIds.indices) {
            val itemUrlsPy = python.getBuiltins().get("list")!!.call()
            if (i < directUrls.size && directUrls[i].isNotBlank()) {
                directUrls[i].split("\t").filter { it.isNotBlank() }.forEach { u ->
                    itemUrlsPy.callAttr("append", u)
                }
            }
            val item = mediaItemClass.call(
                i + 1,
                kinds[i],
                itemUrlsPy,
                names[i],
                formatIds[i]
            )
            mediaItemsPyList.callAttr("append", item)
        }

        val rawDict = python.getBuiltins().get("dict")!!.call()
        rawDict.callAttr("__setitem__", "webpage_url", url)

        val headersDict = python.getBuiltins().get("dict")!!.call()
        if (platform.contains("douyin", ignoreCase = true) || url.contains("douyin", ignoreCase = true)) {
            headersDict.callAttr("__setitem__", "User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0")
            headersDict.callAttr("__setitem__", "Referer", "https://www.douyin.com/")
        }

        val parseResult = parseResultClass.call(
            url,
            platform,
            if (platform.contains("douyin", ignoreCase = true)) "douyin" else if (platform.contains("jm", ignoreCase = true)) "jm" else "yt-dlp",
            title,
            "", // author
            "", // desc
            "", // timestamp
            0,  // duration
            python.getBuiltins().get("list")!!.call(), // covers
            mediaItemsPyList,
            headersDict, // video_headers
            headersDict, // image_headers
            rawDict,
            null // error
        )

        // Progress callback to Kotlin
        val progressCallback = { labelPy: Any?, downloadedBytesPy: Any?, totalBytesPy: Any? ->
            val label = labelPy?.toString() ?: ""
            val downloadedBytes = downloadedBytesPy?.toString()?.toLongOrNull() ?: 0L
            val totalBytes = totalBytesPy?.toString()?.toLongOrNull() ?: 0L
            
            // Update notification
            val pct = if (totalBytes > 0) (downloadedBytes * 100 / totalBytes).toInt() else 0
            updateNotification("Downloading: $title ($pct%)", downloadedBytes, totalBytes)
            
            DownloadTracker.updateProgress(
                label,
                DownloadProgress(label, downloadedBytes, totalBytes, isFinished = false)
            )
        }

        // Initialize Downloader
        val downloaderClass = ydlModule.get("YdlDownloader")!!
        val downloader = downloaderClass.call(
            downloadFolder.absolutePath,
            Kwarg("proxy", proxy),
            Kwarg("timeout", 60.0),
            Kwarg("cookies_from_browser", ""),
            Kwarg("cookies_file", cookiesFile)
        )

        try {
            // Call download_result_sync
            val summary = downloader!!.callAttr(
                "download_result_sync",
                parseResult,
                mediaItemsPyList,
                progressCallback,
                null // control
            )
            
            val errors = summary!!.get("errors")!!.asList()
            if (errors.isNotEmpty()) {
                val errMsg = errors.joinToString("\n") { it.toString() }
                DownloadTracker.updateProgress(
                    title,
                    DownloadProgress(title, 0, 0, isFinished = true, isFailed = true, errorMsg = errMsg)
                )
            } else {
                val filesListPy = summary!!.get("files")?.asList() ?: emptyList()
                val filePaths = filesListPy.mapNotNull { filePy ->
                    val tempPath = filePy?.get("path")?.toString() ?: return@mapNotNull null
                    val kind = filePy?.get("kind")?.toString() ?: "video"
                    val tempFile = File(tempPath)
                    if (tempFile.exists()) {
                        saveFileToMediaStore(this@DownloadService, tempFile, kind)
                    } else {
                        null
                    }
                }

                DownloadTracker.updateProgress(
                    title,
                    DownloadProgress(title, 100, 100, isFinished = true, filePaths = filePaths)
                )
            }
        } catch (e: Exception) {
            DownloadTracker.updateProgress(
                title,
                DownloadProgress(title, 0, 0, isFinished = true, isFailed = true, errorMsg = e.message)
            )
        }
    }

    private fun createNotification(content: String, progress: Long, max: Long): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Video Downloader")
            .setContentText(content)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(pendingIntent)
            .setOngoing(true)

        if (max > 0) {
            builder.setProgress(max.toInt(), progress.toInt(), false)
        } else {
            builder.setProgress(100, 0, true)
        }

        return builder.build()
    }

    private fun updateNotification(content: String, progress: Long, max: Long) {
        val notification = createNotification(content, progress, max)
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, notification)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "Video Downloader Channel",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(serviceChannel)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceJob.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
