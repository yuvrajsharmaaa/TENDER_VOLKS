"""
tender_text_extractor.py
========================
Unified, shared text extraction and font glyph repair engine for Tender Volks.
Used by both `build_sft_dataset.py` and `build_dapt_corpus.py`.

Features:
1. GeM Custom 8-bit Font Glyph Normalization (repairs Hindi bilingual headers,
   broken conjuncts, embedded punctuation, and detached matras).
2. Checkbox & Wingdings symbol normalization (\\uf050, \\uf0fe -> [X], \\uf04f -> [ ]).
3. Pagination & Boilerplate cleanup.
4. Non-printable ASCII ligature control character stripping.
5. Scrambled / garbage text quality detection.
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


# ---------------------------------------------------------------------------
# GeM Custom 8-bit Font Glyph Replacement Table
# ---------------------------------------------------------------------------
GEM_FONT_REPLACEMENTS = [
    # Multi-word & Compound phrases
    ("बड ववरण", "बिड विवरण"),
    ("मं ालय/रा!य का नाम", "मंत्रालय/राज्य का नाम"),
    ("मं ालय/रा!य", "मंत्रालय/राज्य"),
    ("मं ालय", "मंत्रालय"),
    ("रा!य का नाम", "राज्य का नाम"),
    ("रा!य", "राज्य"),
    ("काया%लय का नाम", "कार्यालय का नाम"),
    ("काया%लय", "कार्यालय"),
    ("व&तु 'ेणी", "वस्तु श्रेणी"),
    ("व&तु", "वस्तु"),
    ("'ेणी", "श्रेणी"),
    ("5ासंिगक 'े,णयाँ", "प्रासंगिक श्रेणियाँ"),
    ("5ासंिगक", "प्रासंगिक"),
    ("'े,णयाँ", "श्रेणियाँ"),
    ("7यूनतम औसत वाष%क टन%ओवर", "न्यूनतम औसत वार्षिक टर्नओवर"),
    ("7यूनतम", "न्यूनतम"),
    ("वाष%क", "वार्षिक"),
    ("टन%ओवर", "टर्नओवर"),
    ("मूल उपकरण िनमा%ता", "मूल उपकरण निर्माता"),
    ("िनमा%ता", "निर्माता"),
    ("उ7हं", "उन्हें"),
    ("अपे,?त वगत अनुभव", "अपेक्षित विगत अनुभव"),
    ("अपे,?त", "अपेक्षित"),
    ("वगत अनुभव", "विगत अनुभव"),
    ("वगत 5दश%न", "विगत प्रदर्शन"),
    ("वगत", "विगत"),
    ("5दश%न", "प्रदर्शन"),
    ("वष= का", "वर्षों का"),
    ("वष=", "वर्षों"),
    ("वषB", "वर्षों"),
    ("बड सं@या", "बिड संख्या"),
    ("सं@या", "संख्या"),
    ("सं=या", "संख्या"),
    ("संCया", "संख्या"),
    ("संGया", "संख्या"),
    ("सं?या", "संख्या"),
    ("ं0य", "संख्या"),
    ("Aदनांक", "दिनांक"),
    ("1दनांक", "दिनांक"),
    ("2दनांक", "दिनांक"),
    ("3दनांक", "दिनांक"),
    ("बड द&तावेज़", "बिड दस्तावेज़"),
    ("द&तावेज़G", "दस्तावेजों"),
    ("द&तावेज़J", "दस्तावेजों"),
    ("द&तावेज़I", "दस्तावेजों"),
    ("द&तावेज़H", "दस्तावेजों"),
    ("द&तावेज़F", "दस्तावेजों"),
    ("द&तावेज़K", "दस्तावेजों"),
    ("द&तावेज़L", "दस्तावेजों"),
    ("द&तावेज़M", "दस्तावेजों"),
    ("द&तावेज़", "दस्तावेज़"),
    ("Eया आप िनवदाकार", "क्या आप निविदाकार"),
    ("Hया आप िनवदाकार", "क्या आप निविदाकार"),
    ("Gया आप िनवदाकार", "क्या आप निविदाकार"),
    ("Fया आप िनवदाकार", "क्या आप निविदाकार"),
    ("Dया आप िनवदाकार", "क्या आप निविदाकार"),
    ("Eया", "क्या"),
    ("Hया", "क्या"),
    ("Gया", "क्या"),
    ("Fया", "क्या"),
    ("Dया", "क्या"),
    ("िनवदाकारG", "निविदाकारों"),
    ("िनवदाकारJ", "निविदाकारों"),
    ("िनवदाकारI", "निविदाकारों"),
    ("िनवदाकारH", "निविदाकारों"),
    ("िनवदाकारF", "निविदाकारों"),
    ("िनवदाकार", "निविदाकार"),
    ("Hारा अपलोड", "द्वारा अपलोड"),
    ("Jारा अपलोड", "द्वारा अपलोड"),
    ("Kारा अपलोड", "द्वारा अपलोड"),
    ("Iारा अपलोड", "द्वारा अपलोड"),
    ("Gारा अपलोड", "द्वारा अपलोड"),
    ("Hारा", "द्वारा"),
    ("Jारा", "द्वारा"),
    ("Kारा", "द्वारा"),
    ("Iारा", "द्वारा"),
    ("Gारा", "द्वारा"),
    (">कए गए", "किए गए"),
    ("=कए गए", "किए गए"),
    ("@कए गए", "किए गए"),
    ("Aकए गए", "किए गए"),
    (">कए", "किए"),
    ("=कए", "किए"),
    ("@कए", "किए"),
    ("Aकए", "किए"),
    (";कया जाना है", "किया जाना है"),
    (";कया", "किया"),
    ("चाहते हK?", "चाहते हैं?"),
    ("चाहते हL?", "चाहते हैं?"),
    ("चाहते हM?", "चाहते हैं?"),
    ("चाहते हJ?", "चाहते हैं?"),
    ("हK?", "हैं?"),
    ("हL?", "हैं?"),
    ("हM?", "हैं?"),
    ("हJ?", "हैं?"),
    ("हK", "हैं"),
    ("हL", "हैं"),
    ("हM", "हैं"),
    ("हJ", "हैं"),
    ("संदभ% मेनू", "संदर्भ मेनू"),
    ("संदभ%", "संदर्भ"),
    ("लाभाथ^ के", "लाभार्थी के"),
    ("लाभाथ^", "लाभार्थी"),
    ("5ाK है", "प्राप्त है"),
    ("5ाK", "प्राप्त"),
    ("5दान क गई है", "प्रदान की गई है"),
    ("5दान", "प्रदान"),
    ("&टाट%अप", "स्टार्टअप"),
    (">दखाना चाहते", "दिखाना चाहते"),
    ("Aदखाना चाहते", "दिखाना चाहते"),
    ("@दखाना चाहते", "दिखाना चाहते"),
    ("=दखाना चाहते", "दिखाना चाहते"),
    (">दखाना", "दिखाना"),
    ("Aदखाना", "दिखाना"),
    ("@दखाना", "दिखाना"),
    ("=दखाना", "दिखाना"),
    ("?डलीवर के ?दन", "डिलीवरी के दिन"),
    ("!डलीवर के !दन", "डिलीवरी के दिन"),
    ("?डलीवर", "डिलीवरी"),
    ("!डलीवर", "डिलीवरी"),
    ("?दन=", "दिनों"),
    (";दन9", "दिनों"),
    (">दनL", "दिनों"),
    ("दनJ", "दिनों"),
    ("दनL", "दिनों"),
    ("दन9", "दिनों"),
    ("दनG", "दिनों"),
    ("?दन", "दिन"),
    ("!दन", "दिन"),
    ("ए7सट<शन", "एक्सटेंशन"),
    ("ए;सट@शन", "एक्सटेंशन"),
    (";कतनी बार", "कितनी बार"),
    ("?कतनी बार", "कितनी बार"),
    (";कतनी", "कितनी"),
    ("?कतनी", "कितनी"),
    ("Wयांकन पद्धति", "मूल्यांकन पद्धति"),
    ("Wयांकन", "मूल्यांकन"),
    ("Oरवस% नीलामी", "रिवर्स नीलामी"),
    ("Oरव", "रिवर्स"),
    ("Oरपो?टiग अिधकार", "रिपोर्टिंग अधिकारी"),
    ("Oरप", "रिपोर्ट"),
    ("तकनीक विशZयाँ", "तकनीकी विशिष्टताएँ"),
    ("विशZयाँ", "विशिष्टताएँ"),
    ("परेषती//रपो?टiग", "परेषिती/रिपोर्टिंग"),
    ("परेषती", "परेषिती"),
    ("कुल मा ा", "कुल मात्रा"),
    ("मा ा", "मात्रा"),
    ("पा ता", "पात्रता"),
    ("अिधकार ", "अधिकारी"),
    ("अिधकार", "अधिकारी"),
    ("अिधसूचना", "अधिसूचना"),
    ("चयिनत", "चयनित"),
    ("प0रणाम", "परिणाम"),
    ("प/रणाम", "परिणाम"),
    ("प1रणाम", "परिणाम"),
    ("वभाग", "विभाग"),
    ("व:ेता", "विक्रेता"),
    ("व;ेता", "विक्रेता"),
    ("व<ेता", "विक्रेता"),
    ("व=ेता", "विक्रेता"),
    ("क तारख", "की तारीख"),
    ("तारख", "तारीख"),
    ("क गई", "की गई"),
    ("बडर का", "बिडर का"),
    ("बडर", "बिडर"),
    ("य&थ", "यथा"),
    ("य1द", "यदि"),
    ("aम", "क्रम"),
    ("Wय", "मूल्य"),
    ("पY", "प्रतिशत"),
    ("म*", "में"),
    ("म)", "में"),
    ("मH", "में"),
    ("मI", "में"),
    ("मK", "में"),
    ("मL", "में"),
]


def repair_gem_font_glyphs(text: str) -> str:
    """Repairs GeM custom 8-bit font glyph corruptions into standard Unicode Devanagari."""
    if not text:
        return ""

    for src, target in GEM_FONT_REPLACEMENTS:
        text = text.replace(src, target)

    # Re-attach split combining vowel signs/matras (e.g. 'क  ा' -> 'का', 'म  ं' -> 'मं')
    text = re.sub(r'([\u0915-\u0939])\s+([\u093E-\u094D\u0901-\u0903])', r'\1\2', text)

    return text


# ---------------------------------------------------------------------------
# Checkbox & Symbol Normalization
# ---------------------------------------------------------------------------
def normalize_symbols_and_checkboxes(text: str) -> str:
    """Normalizes checkbox glyphs and Wingdings to readable text."""
    if not text:
        return ""
    text = text.replace("\uf050", " [X] ").replace("\uf0fe", " [X] ").replace("\u2611", " [X] ")
    text = text.replace("\uf04f", " [ ] ").replace("\u2610", " [ ] ")
    return text


# ---------------------------------------------------------------------------
# Quality / Garbage Detection
# ---------------------------------------------------------------------------
def is_text_scrambled_or_garbage(text: str) -> bool:
    """Detects if native PDF text is scrambled or severely corrupted."""
    if not text:
        return True
    if text.count("(cid:") > 3:
        return True
    cleaned = text.strip()
    if not cleaned:
        return True
    total_len = len(cleaned)
    valid_count = sum(1 for c in cleaned if c.isalnum() or c.isspace() or '\u0900' <= c <= '\u097F')
    if (valid_count / total_len) < 0.55:
        return True
    return False


# ---------------------------------------------------------------------------
# Cleaning Pipeline
# ---------------------------------------------------------------------------
RE_PAGINATION_1 = re.compile(r'(?i)\bPage\s+\d+\s+(?:of|/)\s+\d+\b')
RE_PAGINATION_2 = re.compile(r'(?i)\bPage\s*[-–—]?\s*\d+\s*[-–—]?\b')
RE_PAGINATION_3 = re.compile(r'(?i)\b(?:Pg|Page)\.?\s*\d+\b')

RE_CID_GLYPHS = re.compile(r'\(cid:\d+\)')
RE_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
RE_EXCESS_NEWLINES = re.compile(r'\n{3,}')
RE_EXCESS_SPACES = re.compile(r'[ \t]{2,}')


def clean_text_block(text: str) -> str:
    """Applies clean-up filters while preserving Hindi, currency, and markdown formatting."""
    if not text:
        return ""

    text = normalize_symbols_and_checkboxes(text)
    text = repair_gem_font_glyphs(text)
    text = RE_CID_GLYPHS.sub('', text)
    text = RE_PAGINATION_1.sub('', text)
    text = RE_PAGINATION_2.sub('', text)
    text = RE_PAGINATION_3.sub('', text)

    text = RE_CONTROL_CHARS.sub('', text)

    lines = [RE_EXCESS_SPACES.sub(' ', line).strip() for line in text.splitlines()]
    text = '\n'.join(line for line in lines if line)
    text = RE_EXCESS_NEWLINES.sub('\n\n', text)
    return text.strip()


def extract_cleaned_page_text(doc: Any, page_idx: int) -> str:
    """
    Extracts, font-repairs, and cleans text from a PDF page object.
    Preserves exact tabular alphanumeric and numeric tokens.
    """
    if doc is None or page_idx >= len(doc):
        return ""

    page = doc[page_idx]
    raw_text = page.get_text()
    if not raw_text:
        return ""

    cleaned_text = clean_text_block(raw_text)
    return cleaned_text
