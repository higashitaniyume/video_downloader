package top.valency.videodownloader.utils

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File

fun shareFile(context: Context, filePath: String) {
    val file = File(filePath)
    if (!file.exists()) {
        Toast.makeText(context, "文件不存在", Toast.LENGTH_SHORT).show()
        return
    }
    try {
        val uri = FileProvider.getUriForFile(
            context,
            "top.valency.videodownloader.fileprovider",
            file
        )
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = context.contentResolver.getType(uri) ?: "*/*"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(intent, "分享文件"))
    } catch (e: Exception) {
        Toast.makeText(context, "分享失败: ${e.message}", Toast.LENGTH_LONG).show()
    }
}

fun openFile(context: Context, filePath: String) {
    val file = File(filePath)
    if (!file.exists()) {
        Toast.makeText(context, "文件不存在", Toast.LENGTH_SHORT).show()
        return
    }
    try {
        val uri = FileProvider.getUriForFile(
            context,
            "top.valency.videodownloader.fileprovider",
            file
        )
        val mimeType = context.contentResolver.getType(uri) ?: "*/*"
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, mimeType)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    } catch (e: Exception) {
        Toast.makeText(context, "无法打开此文件或未安装对应应用", Toast.LENGTH_LONG).show()
    }
}

fun openFolder(context: Context, filePath: String) {
    try {
        val file = File(filePath)
        val folderName = file.parentFile?.name ?: "VideoDownloader"
        val parentFolder = file.parentFile?.parentFile?.name ?: "Movies"
        val folderUri = Uri.parse("content://com.android.externalstorage.documents/document/primary%3A${parentFolder}%2F${folderName}")
        
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(folderUri, "vnd.android.document/directory")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    } catch (e: Exception) {
        val file = File(filePath)
        val parentFolder = file.parentFile?.parentFile?.name ?: "Movies"
        val folderName = file.parentFile?.name ?: "VideoDownloader"
        Toast.makeText(context, "文件保存在: 内部存储/${parentFolder}/${folderName}", Toast.LENGTH_LONG).show()
    }
}

fun saveFileToMediaStore(context: Context, tempFile: File, kind: String): String? {
    val resolver = context.contentResolver
    val fileName = tempFile.name
    val ext = tempFile.extension.lowercase()

    if (tempFile.isDirectory) {
        // 目录（如漫画图片文件夹）：直接复制到公共 Pictures/VideoDownloader 目录
        try {
            val publicDir = File(
                android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_PICTURES),
                "VideoDownloader/$fileName"
            ).apply { mkdirs() }
            tempFile.copyRecursively(publicDir, overwrite = true)
            // 扫描所有文件使系统相册可见
            val files = publicDir.walkTopDown().filter { it.isFile }.map { it.absolutePath }.toList().toTypedArray()
            if (files.isNotEmpty()) {
                android.media.MediaScannerConnection.scanFile(context, files, null, null)
            }
            return publicDir.absolutePath
        } catch (e: Exception) {
            e.printStackTrace()
            return tempFile.absolutePath
        }
    }

    val actualKind = when (ext) {
        "pdf" -> "pdf"
        "jpg", "jpeg", "png", "webp", "gif", "bmp", "heic", "heif" -> "image"
        "mp3", "m4a", "wav", "aac", "flac", "ogg", "opus" -> "audio"
        "mp4", "mkv", "webm", "avi", "mov", "flv", "3gp", "ts" -> "video"
        else -> kind.lowercase()
    }

    val mimeType = when (ext) {
        "pdf" -> "application/pdf"
        "mp4" -> "video/mp4"
        "mkv" -> "video/x-matroska"
        "webm" -> if (actualKind == "audio") "audio/webm" else "video/webm"
        "avi" -> "video/x-msvideo"
        "mov" -> "video/quicktime"
        "flv" -> "video/x-flv"
        "mp3" -> "audio/mpeg"
        "m4a" -> "audio/mp4"
        "wav" -> "audio/wav"
        "aac" -> "audio/aac"
        "flac" -> "audio/flac"
        "ogg", "opus" -> "audio/ogg"
        "jpg", "jpeg" -> "image/jpeg"
        "png" -> "image/png"
        "webp" -> "image/webp"
        "gif" -> "image/gif"
        "bmp" -> "image/bmp"
        "heic" -> "image/heic"
        "heif" -> "image/heif"
        else -> when (actualKind) {
            "pdf" -> "application/pdf"
            "image" -> "image/jpeg"
            "audio" -> "audio/mpeg"
            "video" -> "video/mp4"
            else -> "application/octet-stream"
        }
    }

    val targetFolder = when (actualKind) {
        "video" -> "Movies"
        "audio" -> "Music"
        "image" -> "Pictures"
        "pdf" -> "Download"
        else -> "Download"
    }
    val subFolder = "VideoDownloader"
    val relativePath = "$targetFolder/$subFolder"

    var resultPath: String? = null

    // 1. Android Q (10) 及以上：使用 MediaStore 插入
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
            put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }

        val collectionUri = when (actualKind) {
            "video" -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            "audio" -> MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
            "image" -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            else -> MediaStore.Downloads.EXTERNAL_CONTENT_URI
        }

        try {
            val itemUri = resolver.insert(collectionUri, contentValues)
            if (itemUri != null) {
                resolver.openOutputStream(itemUri)?.use { outStream ->
                    tempFile.inputStream().use { inStream ->
                        inStream.copyTo(outStream)
                    }
                }

                contentValues.clear()
                contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
                resolver.update(itemUri, contentValues, null, null)

                val projection = arrayOf(MediaStore.MediaColumns.DATA)
                resolver.query(itemUri, projection, null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val dataIndex = cursor.getColumnIndex(MediaStore.MediaColumns.DATA)
                        if (dataIndex >= 0) {
                            resultPath = cursor.getString(dataIndex)
                        }
                    }
                }
                if (resultPath.isNullOrBlank()) {
                    resultPath = File(
                        android.os.Environment.getExternalStoragePublicDirectory(targetFolder),
                        "$subFolder/$fileName"
                    ).absolutePath
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // 2. 兜底处理（或 Android 9 及以下）：直接保存到外部公共存储目录
    if (resultPath.isNullOrBlank()) {
        try {
            val publicDir = File(
                android.os.Environment.getExternalStoragePublicDirectory(targetFolder),
                subFolder
            ).apply { mkdirs() }
            val destFile = File(publicDir, fileName)
            tempFile.copyTo(destFile, overwrite = true)
            resultPath = destFile.absolutePath
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // 3. 触发系统媒体库扫描（MediaScanner），确保相册和播放器立刻显示
    if (!resultPath.isNullOrBlank()) {
        try {
            android.media.MediaScannerConnection.scanFile(
                context,
                arrayOf(resultPath),
                arrayOf(mimeType),
                null
            )
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // 4. 清理临时缓存文件
    try {
        tempFile.delete()
    } catch (e: Exception) {}

    return resultPath
}
