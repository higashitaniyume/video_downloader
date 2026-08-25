package top.valency.videodownloader.models

import java.util.UUID

data class MediaItemUi(
    val parentUrl: String = "",
    val index: Int,
    val kind: String,
    val name: String,
    val formatId: String,
    val urls: List<String> = emptyList()
)

data class ParseResultUi(
    val id: String = UUID.randomUUID().toString(),
    val url: String,
    val platform: String,
    val title: String,
    val author: String = "",
    val desc: String = "",
    val durationText: String = "",
    val items: List<MediaItemUi>,
    val coverUrl: String
)
