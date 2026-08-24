package top.valency.videodownloader.models

data class MediaItemUi(
    val index: Int,
    val kind: String,
    val name: String,
    val formatId: String
)

data class ParseResultUi(
    val url: String,
    val platform: String,
    val title: String,
    val durationText: String,
    val items: List<MediaItemUi>,
    val coverUrl: String
)
