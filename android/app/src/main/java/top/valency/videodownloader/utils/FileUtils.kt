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
    val mimeType = when (tempFile.extension.lowercase()) {
        "mp4" -> "video/mp4"
        "mkv" -> "video/x-matroska"
        "webm" -> "video/webm"
        "mp3" -> "audio/mpeg"
        "m4a" -> "audio/mp4"
        "wav" -> "audio/wav"
        "jpg", "jpeg" -> "image/jpeg"
        "png" -> "image/png"
        else -> "*/*"
    }

    val contentValues = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
        put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val relativePath = when (kind.lowercase()) {
                "video" -> "Movies/VideoDownloader"
                "audio" -> "Music/VideoDownloader"
                "image" -> "Pictures/VideoDownloader"
                else -> "Download/VideoDownloader"
            }
            put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
    }

    val collectionUri = when (kind.lowercase()) {
        "video" -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        "audio" -> MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        "image" -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        else -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Downloads.EXTERNAL_CONTENT_URI
        } else {
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        }
    }

    try {
        val itemUri = resolver.insert(collectionUri, contentValues) ?: return null
        resolver.openOutputStream(itemUri)?.use { outStream ->
            tempFile.inputStream().use { inStream ->
                inStream.copyTo(outStream)
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            contentValues.clear()
            contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(itemUri, contentValues, null, null)
        }

        // Retrieve physical file path
        var physicalPath: String? = null
        val projection = arrayOf(MediaStore.MediaColumns.DATA)
        resolver.query(itemUri, projection, null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val dataIndex = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATA)
                physicalPath = cursor.getString(dataIndex)
            }
        }
        
        // Clean up temporary file
        try {
            tempFile.delete()
        } catch (e: Exception) {}

        return physicalPath
    } catch (e: Exception) {
        e.printStackTrace()
        return null
    }
}
