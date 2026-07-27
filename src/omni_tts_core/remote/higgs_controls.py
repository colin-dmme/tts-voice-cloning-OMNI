"""Declarative Higgs control catalog shared by every UI."""

HIGGS_RESPONSE_FORMAT_CHOICES = (
    ("PCM 16-bit (stream)", "pcm"),
    ("WAV", "wav"),
    ("MP3", "mp3"),
    ("FLAC", "flac"),
    ("Opus", "opus"),
    ("AAC", "aac"),
)

HIGGS_EMOTION_CHOICES = (
    ("Mặc định", ""),
    *((value, value) for value in (
        "elation",
        "amusement",
        "enthusiasm",
        "determination",
        "pride",
        "contentment",
        "affection",
        "relief",
        "contemplation",
        "confusion",
        "surprise",
        "awe",
        "longing",
        "arousal",
        "anger",
        "fear",
        "disgust",
        "bitterness",
        "sadness",
        "shame",
        "helplessness",
    )),
)

HIGGS_STYLE_CHOICES = (
    ("Mặc định", ""),
    ("Singing", "singing"),
    ("Shouting", "shouting"),
    ("Whispering", "whispering"),
)

HIGGS_SPEED_CHOICES = (
    ("Mặc định", ""),
    ("Rất chậm", "speed_very_slow"),
    ("Chậm", "speed_slow"),
    ("Nhanh", "speed_fast"),
    ("Rất nhanh", "speed_very_fast"),
)

HIGGS_PITCH_CHOICES = (
    ("Mặc định", ""),
    ("Thấp", "pitch_low"),
    ("Cao", "pitch_high"),
)

HIGGS_EXPRESSIVENESS_CHOICES = (
    ("Mặc định", ""),
    ("Biểu cảm cao", "expressive_high"),
    ("Biểu cảm thấp", "expressive_low"),
)

# Merely the initial visible values when optional sampling fields are disabled.
# Disabled values are not sent to the server.
HIGGS_OPTIONAL_SAMPLING_DISPLAY = {
    "top_p": 0.95,
    "top_k": 50,
}
