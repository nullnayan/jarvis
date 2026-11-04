# FILE: utils/digits.py
# Converts spoken digit words (as Whisper may transcribe them) to a digit string.

# Words that map to digits (Whisper may transcribe spoken digits as words)
WORD_MAP = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "four": "4", "for": "4",
    "five": "5", "six": "6", "seven": "7",
    "eight": "8", "ate": "8", "nine": "9",
    "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
}


def spoken_to_digits(text: str) -> str:
    """Converts spoken digit words in an utterance to a compact digit string.

    "double zero one one" -> "0011"; "one one one one" -> "1111".
    Non-digit words are dropped, plain digits pass through.
    """
    lower = (text or "").lower().strip()
    words = lower.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        if word in ("double", "twice") and i + 1 < len(words):
            nxt = words[i + 1]
            if nxt in WORD_MAP:
                out.append(WORD_MAP[nxt] * 2)
                i += 2
                continue
            if nxt.isdigit():
                out.append(nxt * 2)
                i += 2
                continue
        if word in WORD_MAP:
            out.append(WORD_MAP[word])
        elif word.isdigit():
            out.append(word)
        i += 1
    return "".join(out)
