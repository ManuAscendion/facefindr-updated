import io
import time
import base64
import pathlib
import tempfile
import sys
from pathlib import Path

import streamlit as st
from PIL import Image

from face_utils import find_matching_images, clear_embedding_cache
from storage import get_event_store, get_photo_store, InvalidImageError, config

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Face Findr ✦",
    page_icon="📸",
    layout="wide",
)

# ── Constants ──────────────────────────────────────────────────────────────────
TMP_DIR  = Path(tempfile.gettempdir())
APP_NAME = "Face Findr"

ADMIN_USERNAME = st.secrets.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

MATCH_THRESHOLD = config.MATCH_THRESHOLD
MAX_WORKERS = config.MAX_WORKERS

# Storage backends — local filesystem today, Azure Blob/Postgres later.
# Nothing below this line touches Path/pickle directly for
# events/photos/cache — it all goes through these two objects.
event_store = get_event_store()
photo_store = get_photo_store()


# ── Video loader helper ────────────────────────────────────────────────────────
def get_video_b64(video_filename: str = "bot.mp4") -> str:
    candidates = [
        pathlib.Path(__file__).parent / "static" / video_filename,
        pathlib.Path("static") / video_filename,
        pathlib.Path(video_filename),
    ]
    for p in candidates:
        if p.exists():
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""


# ── GLOBAL CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Caveat:wght@600;700&display=swap" rel="stylesheet">

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

.stApp {
    background: #FDFAF4;
    font-family: 'Nunito', sans-serif;
}
section[data-testid="stSidebar"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 2rem 4rem !important; max-width: 1200px; }

h1,h2,h3,p,label,span,div { font-family: 'Nunito', sans-serif; }
.stMarkdown p { color: #3d3929 !important; }

.stTextInput > div > div > input {
    background: #fff !important;
    border: 2.5px solid #e8e0cc !important;
    border-radius: 14px !important;
    color: #2d2a1e !important;
    font-family: 'Nunito', sans-serif !important;
    font-size: 15px !important;
    padding: 10px 16px !important;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.stTextInput > div > div > input:focus {
    border-color: #FF6B6B !important;
    box-shadow: 0 0 0 4px rgba(255,107,107,0.15) !important;
}
.stTextInput label {
    color: #7a6f55 !important;
    font-size: 13px !important;
    font-weight: 700 !important;
}
.stTextInput > div > div > input::placeholder {
    color: #a09070 !important;
    opacity: 1 !important;
}

.stSelectbox label {
    color: #7a6f55 !important;
    font-size: 13px !important;
    font-weight: 700 !important;
}
.stSelectbox [data-baseweb="select"] > div:first-child {
    background: #fff !important;
    border: 2.5px solid #e8e0cc !important;
    border-radius: 14px !important;
    font-family: 'Nunito', sans-serif !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #000000 !important;
    padding: 10px 16px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06) !important;
    cursor: pointer !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.stSelectbox [data-baseweb="select"] * {
    color: #000000 !important;
    opacity: 1 !important;
}
.stSelectbox [data-baseweb="select"] > div:first-child:hover {
    border-color: #FF6B6B !important;
    box-shadow: 0 3px 10px rgba(255,107,107,0.15) !important;
}
.stSelectbox [data-baseweb="select"] svg {
    fill: #FF6B6B !important;
    width: 18px !important;
    height: 18px !important;
}

.stButton > button {
    font-family: 'Nunito', sans-serif !important;
    font-weight: 800 !important;
    border-radius: 14px !important;
    border: 2.5px solid transparent !important;
    padding: 11px 22px !important;
    font-size: 15px !important;
    transition: all 0.18s ease !important;
    width: 100%;
    background: #FF6B6B !important;
    color: #fff !important;
    box-shadow: 0 4px 0 #d94f4f !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 0 #d94f4f !important;
    background: #ff5252 !important;
}
.stButton > button:active {
    transform: translateY(1px) !important;
    box-shadow: 0 2px 0 #d94f4f !important;
}
.stButton > button:disabled {
    background: #e8e0cc !important;
    color: #b5a98a !important;
    box-shadow: 0 4px 0 #d4cbb5 !important;
}

.consent-btn-wrapper .stButton > button {
    background: #f5f0e8 !important;
    color: #7a6f55 !important;
    border: 2px solid #d4cbb5 !important;
    box-shadow: 0 2px 0 #c4bba5 !important;
    border-radius: 10px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    padding: 7px 16px !important;
    width: auto !important;
}
.consent-btn-wrapper .stButton > button:hover {
    background: #ede8de !important;
    color: #3d3929 !important;
    border-color: #b5a98a !important;
    box-shadow: 0 3px 0 #b5a98a !important;
    transform: translateY(-1px) !important;
}
.consent-btn-agreed .stButton > button {
    background: #f0fdf4 !important;
    color: #1e7a3a !important;
    border: 2px solid #9de0af !important;
    box-shadow: 0 2px 0 #7acc92 !important;
    border-radius: 10px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    padding: 7px 16px !important;
    width: auto !important;
}
.consent-btn-agreed .stButton > button:hover {
    background: #e0f9ea !important;
    color: #155a2a !important;
    border-color: #6dc88a !important;
    box-shadow: 0 3px 0 #6dc88a !important;
    transform: translateY(-1px) !important;
}

.danger-btn .stButton > button {
    background: #fff0f0 !important;
    color: #c0392b !important;
    border: 2px solid #f5a6a6 !important;
    box-shadow: 0 2px 0 #e08080 !important;
    font-size: 13px !important;
}
.danger-btn .stButton > button:hover {
    background: #fde8e8 !important;
    border-color: #e07070 !important;
    transform: translateY(-1px) !important;
}

.secondary-btn .stButton > button {
    background: #f5f0e8 !important;
    color: #7a6f55 !important;
    border: 2px solid #d4cbb5 !important;
    box-shadow: 0 2px 0 #c4bba5 !important;
    font-size: 13px !important;
    font-weight: 700 !important;
}
.secondary-btn .stButton > button:hover {
    background: #ede8de !important;
    color: #3d3929 !important;
    border-color: #b5a98a !important;
    transform: translateY(-1px) !important;
}

.admin-action-btn .stButton > button {
    background: #fff !important;
    color: #2d2a1e !important;
    border: 2px solid #e8e0cc !important;
    box-shadow: 0 2px 0 #d4cbb5 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    padding: 6px 12px !important;
    border-radius: 10px !important;
    width: auto !important;
}
.admin-action-btn .stButton > button:hover {
    border-color: #FF6B6B !important;
    color: #FF6B6B !important;
    box-shadow: 0 2px 0 #d94f4f !important;
    transform: translateY(-1px) !important;
}
.admin-action-btn-active .stButton > button {
    background: #f0fdf4 !important;
    color: #1e7a3a !important;
    border: 2px solid #9de0af !important;
    box-shadow: 0 2px 0 #7acc92 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    padding: 6px 12px !important;
    border-radius: 10px !important;
    width: auto !important;
}
.admin-del-btn .stButton > button {
    background: #fff0f0 !important;
    color: #c0392b !important;
    border: 2px solid #f5a6a6 !important;
    box-shadow: 0 2px 0 #e08080 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    padding: 6px 12px !important;
    border-radius: 10px !important;
    width: auto !important;
}
.admin-del-btn .stButton > button:hover {
    background: #fde8e8 !important;
    border-color: #e07070 !important;
    transform: translateY(-1px) !important;
}
.photo-del-btn { display: flex; justify-content: flex-end; margin-top: -6px; }
.photo-del-btn .stButton > button {
    background: transparent !important;
    color: #b5342a !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 4px 6px !important;
    width: auto !important;
    opacity: 0.65;
    transition: opacity 0.15s ease, color 0.15s ease !important;
}
.photo-del-btn .stButton > button:hover {
    opacity: 1;
    color: #c0392b !important;
    background: transparent !important;
    transform: none !important;
}
.upload-btn .stButton > button {
    background: #FF6B6B !important;
    color: #fff !important;
    border: none !important;
    box-shadow: 0 3px 0 #d94f4f !important;
    font-size: 13px !important;
    font-weight: 800 !important;
    padding: 9px 18px !important;
    border-radius: 12px !important;
    width: 100% !important;
}
.upload-btn .stButton > button:hover {
    background: #ff5252 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 0 #d94f4f !important;
}
.upload-btn .stButton > button:disabled {
    background: #e8e0cc !important;
    color: #b5a98a !important;
    box-shadow: 0 3px 0 #d4cbb5 !important;
}
.clear-photos-btn .stButton > button {
    background: #fff0f0 !important;
    color: #c0392b !important;
    border: 2px solid #f5a6a6 !important;
    box-shadow: 0 2px 0 #e08080 !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    padding: 9px 18px !important;
    border-radius: 12px !important;
    width: 100% !important;
}
.clear-photos-btn .stButton > button:hover {
    background: #fde8e8 !important;
    border-color: #e07070 !important;
    transform: translateY(-1px) !important;
}
.clear-photos-btn .stButton > button:disabled {
    background: #f5f0e8 !important;
    color: #c4bba5 !important;
    border-color: #e0dbd0 !important;
    box-shadow: none !important;
}
.cache-btn .stButton > button {
    background: #f5f0e8 !important;
    color: #7a6f55 !important;
    border: 2px solid #d4cbb5 !important;
    box-shadow: 0 2px 0 #c4bba5 !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    padding: 9px 18px !important;
    border-radius: 12px !important;
    width: 100% !important;
}
.cache-btn .stButton > button:hover {
    background: #ede8de !important;
    color: #3d3929 !important;
    border-color: #b5a98a !important;
    transform: translateY(-1px) !important;
}

.stSlider > div > div > div > div { background: #FF6B6B !important; }
.stSlider label { color: #7a6f55 !important; font-size: 13px !important; font-weight: 700 !important; }

.stCheckbox { margin-top: 6px !important; }
.stCheckbox [data-baseweb="checkbox"] > div:first-child { display: none !important; }
.stCheckbox [data-baseweb="checkbox"] svg { display: none !important; }
.stCheckbox input[type="checkbox"] { display: none !important; }
.stCheckbox label { color: #2d2a1e !important; font-size: 15px !important; font-weight: 700 !important; cursor: pointer !important; }

.stFileUploader > div {
    background: #fff !important;
    border: 2.5px dashed #d4cbb5 !important;
    border-radius: 16px !important;
}
.stFileUploader > div:hover { border-color: #FF6B6B !important; }
.stFileUploader label { color: #7a6f55 !important; font-weight: 700 !important; }

.stProgress > div > div > div { background: #FF6B6B !important; border-radius: 100px; }

.pill-ok   { background:#e8f8ec; color:#1e7a3a; border:2px solid #9de0af; border-radius:12px; padding:10px 16px; font-size:13px; font-weight:700; margin-top:10px; line-height:1.5; }
.pill-err  { background:#fdeaea; color:#c0392b; border:2px solid #f5a6a6; border-radius:12px; padding:10px 16px; font-size:13px; font-weight:700; margin-top:10px; line-height:1.5; }
.pill-info { background:#fef9e7; color:#9a6f00; border:2px solid #f5dfa0; border-radius:12px; padding:10px 16px; font-size:13px; font-weight:700; margin-top:10px; line-height:1.5; }
.pill-warn { background:#fff4e0; color:#b35a00; border:2px solid #ffc87a; border-radius:12px; padding:10px 16px; font-size:13px; font-weight:700; margin-top:10px; line-height:1.5; }

.fun-card {
    background: #fff;
    border: 2.5px solid #e8e0cc;
    border-radius: 24px;
    padding: 28px;
    margin-bottom: 20px;
    position: relative;
}
.fun-card-yellow { background: #FFFBEC; border-color: #FFE066; }
.fun-card-blue   { background: #EEF4FF; border-color: #B3CFFF; }
.fun-card-green  { background: #F0FDF4; border-color: #9DE0AF; }

.nav-tab-btn .stButton > button {
    background: #fff !important;
    color: #7a6f55 !important;
    border: 2.5px solid #e8e0cc !important;
    box-shadow: none !important;
    border-radius: 14px !important;
    font-weight: 800 !important;
    font-size: 15px !important;
    padding: 10px 24px !important;
    width: auto !important;
    transition: all 0.18s ease !important;
}
.nav-tab-btn .stButton > button:hover {
    color: #FF6B6B !important;
    border-color: #FF6B6B !important;
    transform: none !important;
}
.nav-tab-btn-active .stButton > button {
    background: #FF6B6B !important;
    color: #fff !important;
    border: 2.5px solid #FF6B6B !important;
    box-shadow: 0 3px 0 #d94f4f !important;
}
.nav-tab-btn-active .stButton > button:hover {
    color: #fff !important;
    background: #ff5252 !important;
    border-color: #ff5252 !important;
}

.cbar-bg   { background:#e8e0cc; border-radius:100px; height:6px; margin-top:6px; overflow:hidden; }
.cbar-fill { background:linear-gradient(90deg,#FF6B6B,#FFD166); height:6px; border-radius:100px; }

.consent-row { display:flex; gap:12px; margin-bottom:12px; align-items:flex-start; font-size:14px; color:#5a5240; line-height:1.6; }
.consent-icon { font-size:18px; flex-shrink:0; margin-top:1px; }

.sticker { display:inline-flex; align-items:center; gap:6px; border-radius:100px; padding:6px 14px; font-size:12px; font-weight:800; letter-spacing:0.3px; }
.sticker-red    { background:#FF6B6B; color:#fff; }
.sticker-yellow { background:#F5A623; color:#fff; }
.sticker-green  { background:#27AE60; color:#fff; }
.sticker-blue   { background:#3B82F6; color:#fff; }
.sticker-purple { background:#8B5CF6; color:#fff; }
.sticker-gray   { background:#9a9080; color:#fff; }

.event-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #fff;
    border: 2px solid #e8e0cc;
    border-radius: 14px;
    padding: 10px 14px;
    margin-bottom: 8px;
    gap: 10px;
    transition: border-color 0.2s;
}
.event-row:hover { border-color: #FF6B6B; }
.event-row-active { border-color: #27AE60 !important; background: #f0fdf4 !important; }
.event-row-name { font-size: 14px; font-weight: 800; color: #2d2a1e; flex: 1; min-width: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-row-count { font-size: 11px; color: #a09070; font-weight: 600; white-space: nowrap; }
.event-row-actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }

.fancy-divider {
    height: 3px;
    background: linear-gradient(90deg,#FF6B6B 0%,#FFD166 33%,#6BCB77 66%,#4D96FF 100%);
    border-radius: 100px;
    margin-bottom: 28px;
    opacity: 0.5;
}

.section-label {
    font-family: 'Caveat', cursive;
    font-size: 20px;
    font-weight: 700;
    color: #2d2a1e;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.action-row {
    display: flex;
    gap: 10px;
    align-items: stretch;
    margin-top: 12px;
    flex-wrap: wrap;
}

.stDownloadButton > button {
    background: #0f172a !important;
    color: #ffffff !important;
    border-radius: 14px !important;
    border: none !important;
    font-family: 'Nunito', sans-serif !important;
    font-weight: 800 !important;
    padding: 11px 22px !important;
    font-size: 15px !important;
    box-shadow: 0 4px 0 #020617 !important;
    transition: all 0.15s ease !important;
}
.stDownloadButton > button:hover {
    background: #0f172a !important;
    color: #ffffff !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 0 #020617 !important;
    cursor: pointer !important;
}
.stDownloadButton > button:active {
    transform: translateY(1px) !important;
    box-shadow: 0 2px 0 #020617 !important;
}

.ff-video-loading-wrap {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #FDFAF4;
    z-index: 99999;
}
.ff-video-loading-inner {
    padding: 40px 24px;
    border: 2.5px solid #e8e0cc;
    border-radius: 28px;
    background: #FDFAF4;
    text-align: center;
    width: 420px;
}
.ff-video-loading-wrap video {
    width: 280px;
    max-width: 100%;
    border-radius: 16px;
    margin-bottom: 16px;
}
.ff-video-title {
    font-family: 'Caveat', cursive;
    font-size: 26px;
    font-weight: 700;
    color: #2d2a1e;
    margin-bottom: 6px;
}
.ff-video-sub {
    font-size: 13px;
    color: #a09070;
    font-weight: 600;
}

@keyframes scan-line {
    0%   { top: 10%; opacity: 1; }
    100% { top: 85%; opacity: 0.3; }
}
@keyframes pulse-ring {
    0%   { transform: scale(0.85); opacity: 0.9; }
    50%  { transform: scale(1.05); opacity: 0.5; }
    100% { transform: scale(0.85); opacity: 0.9; }
}
@keyframes dot-bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40%            { transform: translateY(-8px); opacity: 1; }
}
@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position:  200% 0; }
}
.ff-loading-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px 40px;
    background: #FDFAF4;
    border: 2.5px solid #e8e0cc;
    border-radius: 28px;
    margin: 24px 0;
    position: relative;
    overflow: hidden;
}
.ff-shimmer-bar {
    position: absolute;
    top: 0; left: 0; right: 0; height: 4px;
    background: linear-gradient(90deg, #e8e0cc 0%, #FF6B6B 40%, #FFD166 60%, #e8e0cc 100%);
    background-size: 200% 100%;
    animation: shimmer 1.6s linear infinite;
    border-radius: 28px 28px 0 0;
}
.ff-face-ring {
    width: 90px; height: 90px;
    border-radius: 50%;
    border: 3px solid #FF6B6B;
    display: flex; align-items: center; justify-content: center;
    animation: pulse-ring 1.8s ease-in-out infinite;
    position: relative;
    margin-bottom: 20px;
    flex-shrink: 0;
}
.ff-face-emoji { font-size: 40px; line-height: 1; }
.ff-scan-line {
    position: absolute;
    left: 8px; right: 8px; height: 2px;
    background: linear-gradient(90deg, transparent, #FF6B6B, transparent);
    border-radius: 2px;
    animation: scan-line 1.4s ease-in-out infinite alternate;
}
.ff-title {
    font-family: 'Caveat', cursive;
    font-size: 26px; font-weight: 700;
    color: #2d2a1e; margin-bottom: 6px; text-align: center;
}
.ff-sub {
    font-size: 13px; color: #a09070;
    font-weight: 600; text-align: center; margin-bottom: 18px;
}
.ff-dots { display: flex; gap: 7px; align-items: center; }
.ff-dot {
    width: 8px; height: 8px;
    background: #FF6B6B; border-radius: 50%;
}
.ff-dot:nth-child(1) { animation: dot-bounce 1.2s ease-in-out infinite 0s; }
.ff-dot:nth-child(2) { animation: dot-bounce 1.2s ease-in-out infinite 0.2s; }
.ff-dot:nth-child(3) { animation: dot-bounce 1.2s ease-in-out infinite 0.4s; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def sanitize_folder_name(name: str) -> str:
    """Strip unsafe characters for folder/event names."""
    safe = "".join(c for c in name if c.isalnum() or c in " _-()").strip()
    return safe[:60] if safe else "Untitled Event"


def render_loading_screen(placeholder):
    video_b64 = get_video_b64("loading.mp4")

    if video_b64:
        placeholder.markdown(f"""
<div class="ff-video-loading-wrap">
    <div class="ff-video-loading-inner">
        <video autoplay loop muted playsinline>
            <source src="data:video/mp4;base64,{video_b64}" type="video/mp4">
        </video>
        <div class="ff-video-title">Scanning your event photos…</div>
        <div class="ff-video-sub">AI is comparing faces — this may take a moment</div>
    </div>
</div>
""", unsafe_allow_html=True)
    else:
        placeholder.markdown("""
        <div class="ff-loading-wrap">
            <div class="ff-shimmer-bar"></div>
            <div class="ff-face-ring">
                <div class="ff-scan-line"></div>
                <span class="ff-face-emoji">🤳</span>
            </div>
            <div class="ff-title">Scanning your event photos…</div>
            <div class="ff-sub">AI is comparing faces — this may take a moment</div>
            <div class="ff-dots">
                <div class="ff-dot"></div>
                <div class="ff-dot"></div>
                <div class="ff-dot"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "admin_logged_in":    False,
    "results":            None,
    "consent_given":      False,
    "admin_active_event": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════
def render_header():
    admin_badge = ""
    if st.session_state.admin_logged_in:
        admin_badge = (
            '<span style="background:#FFE066;color:#7a5c00;font-size:11px;font-weight:900;'
            'letter-spacing:1px;padding:3px 10px;border-radius:100px;'
            'border:1.5px solid #FFD000;margin-left:10px;vertical-align:middle">ADMIN</span>'
        )

    event_names = event_store.list_events()
    total_events = len(event_names)
    total_photos = sum(event_store.count_photos(name) for name in event_names)

    if total_events:
        photos_badge = (
            f'<span class="sticker sticker-green">'
            f'{total_events} event{"s" if total_events != 1 else ""} · {total_photos} photos</span>'
        )
    else:
        photos_badge = '<span class="sticker sticker-red">No events yet</span>'

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;padding:28px 0 10px;flex-wrap:wrap">
        <div style="position:relative;width:52px;height:52px;flex-shrink:0">
            <div style="width:52px;height:52px;background:#FF6B6B;border-radius:16px;
                        display:flex;align-items:center;justify-content:center;
                        font-size:26px;box-shadow:0 4px 0 #d94f4f">📸</div>
            <div style="position:absolute;bottom:-4px;right:-6px;width:20px;height:20px;
                        background:#FFD166;border-radius:50%;border:2px solid #FDFAF4;
                        display:flex;align-items:center;justify-content:center;font-size:10px">✦</div>
        </div>
        <div>
            <div style="font-family:'Caveat',cursive;font-size:34px;font-weight:700;
                        color:#2d2a1e;line-height:1;letter-spacing:-0.5px">
                Face Findr {admin_badge}
            </div>
            <div style="font-size:12px;color:#a09070;font-weight:700;letter-spacing:0.8px;margin-top:2px">
                Find yourself in every memory
            </div>
        </div>
        <div style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            <span class="sticker sticker-yellow">Multi-Event</span>
            <span class="sticker sticker-purple">AI-Powered</span>
            {photos_badge}
        </div>
    </div>
    <div class="fancy-divider"></div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  USER TAB
# ══════════════════════════════════════════════════════════════════════════════
def render_user_tab():

    st.markdown("""
    <div style="display:flex;align-items:flex-start;gap:24px;margin-bottom:32px;flex-wrap:wrap">
        <div style="flex:1;min-width:280px">
            <div style="font-family:'Caveat',cursive;font-size:46px;font-weight:700;
                        color:#2d2a1e;line-height:1.05;margin-bottom:12px">
                Find yourself<br>
                <span style="color:#FF6B6B">in every shot</span>
            </div>
            <div style="font-size:15px;color:#7a6f55;line-height:1.7;max-width:460px">
                Access your event photos effortlessly. Capture a selfie and our system will identify and return all images where you appear.
                Live camera only — no file uploads,
                no stored data, no fuss.
            </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;padding-top:8px">
            <div style="display:flex;align-items:center;gap:10px;background:#fff;
                        border:2px solid #FFD4D4;border-radius:100px;padding:8px 18px 8px 8px">
                <div style="width:28px;height:28px;background:#FF6B6B;border-radius:50%;
                            display:flex;align-items:center;justify-content:center;
                            font-size:13px;font-weight:800;color:#fff;flex-shrink:0">1</div>
                <span style="font-size:14px;font-weight:700;color:#3d3929">Read and agree to the consent</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;background:#fff;
                        border:2px solid #B3CFFF;border-radius:100px;padding:8px 18px 8px 8px">
                <div style="width:28px;height:28px;background:#3B82F6;border-radius:50%;
                            display:flex;align-items:center;justify-content:center;
                            font-size:13px;font-weight:800;color:#fff;flex-shrink:0">2</div>
                <span style="font-size:14px;font-weight:700;color:#3d3929">Select your event from the list</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;background:#fff;
                        border:2px solid #FFE5A0;border-radius:100px;padding:8px 18px 8px 8px">
                <div style="width:28px;height:28px;background:#F5A623;border-radius:50%;
                            display:flex;align-items:center;justify-content:center;
                            font-size:13px;font-weight:800;color:#fff;flex-shrink:0">3</div>
                <span style="font-size:14px;font-weight:700;color:#3d3929">Take your selfie live via camera</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;background:#fff;
                        border:2px solid #A8E6BC;border-radius:100px;padding:8px 18px 8px 8px">
                <div style="width:28px;height:28px;background:#27AE60;border-radius:50%;
                            display:flex;align-items:center;justify-content:center;
                            font-size:13px;font-weight:800;color:#fff;flex-shrink:0">4</div>
                <span style="font-size:14px;font-weight:700;color:#3d3929">Download your photos!</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    loading_placeholder = st.empty()
    left, right = st.columns([1.05, 1], gap="large")

    with left:
        st.markdown("""
        <div class="fun-card fun-card-yellow">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px">
                <div style="width:42px;height:42px;background:#FF6B6B;border-radius:12px;
                            display:flex;align-items:center;justify-content:center;flex-shrink:0">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                        <rect x="5" y="11" width="14" height="10" rx="2.5" fill="white"/>
                        <path d="M8 11V7.5a4 4 0 0 1 8 0V11" stroke="white" stroke-width="2.2"
                              stroke-linecap="round" fill="none"/>
                        <circle cx="12" cy="16" r="1.5" fill="#FF6B6B"/>
                    </svg>
                </div>
                <div>
                    <div style="font-family:'Caveat',cursive;font-size:22px;font-weight:700;color:#2d2a1e">
                        Privacy &amp; Consent Notice
                    </div>
                    <div style="font-size:12px;color:#9a7a20;font-weight:700;margin-top:1px">
                        Your data stays yours — always
                    </div>
                </div>
            </div>
            <div style="font-size:13px;color:#7a6a3a;margin-bottom:16px;font-weight:600">
                By proceeding, you agree to all of the following:
            </div>
            <div class="consent-row">
                <span class="consent-icon">📸</span>
                <span>I <strong>voluntarily consent</strong> to the live camera capture of my selfie
                by <strong>Face Findr</strong>. I understand this is a live capture, not a file upload.</span>
            </div>
            <div class="consent-row">
                <span class="consent-icon">🧭</span>
                <span>My image will be used <strong>only</strong> for real-time identification
                and retrieval of my event photos — nothing else.</span>
            </div>
            <div class="consent-row">
                <span class="consent-icon">⏳</span>
                <span>My photo is <strong>processed temporarily</strong> and will <strong>not</strong>
                be stored, saved, or retained after processing is complete.</span>
            </div>
            <div class="consent-row">
                <span class="consent-icon">🛡️</span>
                <span>My data will <strong>not</strong> be used for profiling, tracking,
                or sharing with any third parties.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        is_checked = st.session_state.consent_given

        check_svg = """<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 7l3.5 3.5L12 3" stroke="white" stroke-width="2.2"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>"""

        if is_checked:
            box_html = f"""
            <div style="display:flex;align-items:center;gap:12px;
                        padding:10px 16px;background:#f0fdf4;
                        border:2px solid #27AE60;border-radius:12px;
                        cursor:pointer;user-select:none;margin-bottom:10px">
                <div style="width:20px;height:20px;border-radius:5px;
                            background:#27AE60;border:2px solid #27AE60;
                            display:flex;align-items:center;justify-content:center;
                            flex-shrink:0">{check_svg}</div>
                <span style="font-size:14px;font-weight:700;color:#1e7a3a">
                    I give my explicit consent for this one-time photo processing.
                </span>
            </div>"""
        else:
            box_html = """
            <div style="display:flex;align-items:center;gap:12px;
                        padding:10px 16px;background:#fff;
                        border:2px solid #e0dbd0;border-radius:12px;
                        cursor:pointer;user-select:none;margin-bottom:10px">
                <div style="width:20px;height:20px;border-radius:5px;
                            background:#fff;border:2.5px solid #aaa89a;
                            flex-shrink:0"></div>
                <span style="font-size:14px;font-weight:700;color:#7a6f55">
                    I give my explicit consent for this one-time photo processing.
                </span>
            </div>"""

        st.markdown(box_html, unsafe_allow_html=True)

        if is_checked:
            st.markdown('<div class="consent-btn-agreed">', unsafe_allow_html=True)
            if st.button("✓ Agreed — click to undo", key="consent_toggle"):
                st.session_state.consent_given = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="consent-btn-wrapper">', unsafe_allow_html=True)
            if st.button("Tap to give consent →", key="consent_toggle"):
                st.session_state.consent_given = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if not st.session_state.consent_given:
            st.markdown(
                '<div class="pill-info" style="margin-top:12px">'
                'Accept the consent above to unlock the event picker and camera.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="pill-ok" style="margin-top:12px">'
                'Consent given — pick your event and take your selfie!</div>',
                unsafe_allow_html=True,
            )

    with right:
        st.markdown("""
        <div style="font-family:'Caveat',cursive;font-size:22px;font-weight:700;
                    color:#2d2a1e;margin-bottom:6px">
            Choose your event
        </div>
        """, unsafe_allow_html=True)

        event_names = event_store.list_events()

        if not event_names:
            st.markdown("""
            <div style="background:#fff4e0;border:2px solid #ffc87a;border-radius:14px;
                        padding:18px 20px;margin-bottom:18px;text-align:center">
                <div style="font-size:28px;margin-bottom:6px">📭</div>
                <div style="font-size:14px;color:#b35a00;font-weight:700">
                    No events available yet. Check back soon!
                </div>
            </div>
            """, unsafe_allow_html=True)
            selected_event_name = None
        else:
            if not st.session_state.consent_given:
                st.markdown("""
                <div style="background:#f5f0e8;border:2.5px dashed #d4cbb5;border-radius:14px;
                            padding:18px 20px;margin-bottom:16px;text-align:center">
                    <div style="font-size:13px;color:#b5a98a;font-weight:700">
                        🔒 Accept consent to unlock event picker
                    </div>
                </div>
                """, unsafe_allow_html=True)
                selected_event_name = None
            else:
                chosen_name = st.selectbox(
                    "Select an event",
                    options=event_names,
                    index=None,
                    key="user_event_select",
                    label_visibility="collapsed",
                    placeholder="Select the event you attended to search only those photos.",
                )
                selected_event_name = chosen_name if chosen_name else None
                if selected_event_name:
                    img_count = event_store.count_photos(selected_event_name)
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;gap:10px;
                                background:#f0fdf4;border:2px solid #9de0af;
                                border-radius:12px;padding:10px 16px;margin-bottom:14px">
                        <span style="font-size:18px">📁</span>
                        <div>
                            <div style="font-size:13px;font-weight:800;color:#1e7a3a">{chosen_name}</div>
                            <div style="font-size:12px;color:#4a9a5a;font-weight:600">
                                {img_count} photo{"s" if img_count != 1 else ""} in this event
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        st.markdown("""
        <div style="font-family:'Caveat',cursive;font-size:22px;font-weight:700;
                    color:#2d2a1e;margin-bottom:6px">
            Take your selfie
        </div>
        <div style="font-size:13px;color:#a09070;font-weight:600;margin-bottom:14px">
            Live camera only — no file uploads allowed for your privacy.
        </div>
        """, unsafe_allow_html=True)

        camera_disabled = not st.session_state.consent_given or selected_event_name is None

        if camera_disabled:
            st.markdown("""
            <div style="background:#f5f0e8;border:2.5px dashed #d4cbb5;border-radius:16px;
                        padding:40px 20px;text-align:center;margin-bottom:16px">
                <div style="font-size:36px;margin-bottom:8px">📷</div>
                <div style="font-size:14px;color:#b5a98a;font-weight:700">
                    Accept consent &amp; pick an event to unlock camera
                </div>
            </div>
            """, unsafe_allow_html=True)
            camera_photo = None
        else:
            camera_photo = st.camera_input(
                "Point your face at the camera",
                key="camera_selfie",
                label_visibility="collapsed",
            )

        threshold = MATCH_THRESHOLD

        if not camera_disabled and camera_photo is not None:
            st.markdown("""
            <div style="display:flex;align-items:center;gap:8px;background:#e8f8ec;
                        border:2px solid #9de0af;border-radius:10px;padding:8px 14px;margin-bottom:12px">
                <span style="font-size:16px">🔒</span>
                <span style="font-size:13px;font-weight:700;color:#1e7a3a">
                    Live capture confirmed — not a file upload
                </span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        can_search = (
            st.session_state.consent_given
            and camera_photo is not None
            and selected_event_name is not None
            and event_store.count_photos(selected_event_name) > 0
        )

        search_clicked = st.button("🔍 Find My Photos", key="search_btn", disabled=not can_search)

        if search_clicked and can_search:
            selfie_bytes = camera_photo.getvalue()
            event_folder_path = str(config.EVENTS_ROOT_DIR / selected_event_name)

            render_loading_screen(loading_placeholder)
            search_started_at = time.time()
            MIN_LOADING_SECONDS = 2.5  # guarantees the loading screen is actually visible

            try:
                results = find_matching_images(
                    selfie_bytes=selfie_bytes,
                    event_folder=event_folder_path,
                    threshold=threshold,
                    tmp_selfie_path=str(TMP_DIR / "facefindr_selfie.jpg"),
                    max_workers=1 if sys.platform == "win32" else MAX_WORKERS,
                )
                st.session_state.results = results

            except ValueError as e:
                elapsed = time.time() - search_started_at
                if elapsed < MIN_LOADING_SECONDS:
                    time.sleep(MIN_LOADING_SECONDS - elapsed)
                loading_placeholder.empty()
                st.markdown(f'<div class="pill-err">{e}</div>', unsafe_allow_html=True)
                st.session_state.results = None

            except Exception as e:
                elapsed = time.time() - search_started_at
                if elapsed < MIN_LOADING_SECONDS:
                    time.sleep(MIN_LOADING_SECONDS - elapsed)
                loading_placeholder.empty()
                st.markdown(f'<div class="pill-err">Something went wrong: {e}</div>', unsafe_allow_html=True)
                st.session_state.results = None

            else:
                elapsed = time.time() - search_started_at
                if elapsed < MIN_LOADING_SECONDS:
                    time.sleep(MIN_LOADING_SECONDS - elapsed)
                loading_placeholder.empty()

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state.results is not None:
        results = st.session_state.results
        st.markdown(
            "<hr style='border:none;border-top:2.5px dashed #e8e0cc;margin:32px 0'>",
            unsafe_allow_html=True,
        )

        if not results:
            st.markdown("""
            <div class="fun-card" style="text-align:center;padding:40px">
                <div style="font-size:48px;margin-bottom:12px">🙈</div>
                <div style="font-family:'Caveat',cursive;font-size:26px;font-weight:700;
                            color:#2d2a1e;margin-bottom:8px">No matches found!</div>
                <div style="font-size:15px;color:#7a6f55;max-width:400px;margin:0 auto">
                    Try retaking your selfie in better lighting and search again.
                    Or maybe you're just camera shy?
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            count = len(results)
            import zipfile
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for match in results:
                    img_path = Path(match["filepath"])
                    if img_path.exists():
                        zf.write(img_path, img_path.name)
            zip_buffer.seek(0)
            header_left, header_right = st.columns([2, 1])
            with header_left:
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding-top:6px">
                    <div style="font-family:'Caveat',cursive;font-size:34px;font-weight:700;color:#2d2a1e">
                        Found you in {count} photo{'s' if count != 1 else ''}!
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with header_right:
                st.markdown('<div style="display:flex;justify-content:flex-end;align-items:center;height:100%;padding-top:8px">', unsafe_allow_html=True)
                st.download_button(
                    "⬇ Download All Photos ",
                    data=zip_buffer,
                    file_name="my_event_photos.zip",
                    mime="application/zip",
                    key="download_all_btn",
                    use_container_width=False,
                )
                st.markdown('</div>', unsafe_allow_html=True)

            grid = st.columns(4)
            for i, match in enumerate(results):
                img_path = Path(match["filepath"])
                if not img_path.exists():
                    continue
                with grid[i % 4]:
                    st.image(Image.open(img_path), use_container_width=True)
                    with open(img_path, "rb") as f:
                        st.download_button(
                            "⬇ Download",
                            data=f.read(),
                            file_name=match["filename"],
                            mime="image/jpeg",
                            key=f"dl_{i}",
                            use_container_width=True,
                        )

        st.markdown("""
        <p style="text-align:center;font-size:12px;color:#c0b090;margin-top:28px">
            Your selfie has been discarded. No personal data was stored.
        </p>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN TAB
# ══════════════════════════════════════════════════════════════════════════════
def render_admin_tab():
    if not st.session_state.admin_logged_in:
        _, mid, _ = st.columns([1, 1.2, 1])
        with mid:
            st.markdown("""
            <div class="fun-card fun-card-blue" style="text-align:center;padding:36px 32px 24px">
                <div style="font-size:48px;margin-bottom:10px">🔐</div>
                <div style="font-family:'Caveat',cursive;font-size:28px;font-weight:700;
                            color:#2d2a1e;margin-bottom:6px">Admin Login</div>
                <div style="font-size:14px;color:#7a6f55;margin-bottom:24px">
                    This area is for event admins only.
                </div>
            </div>
            """, unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="admin", key="login_user")
            password = st.text_input("Password", type="password", placeholder="••••••••", key="login_pass")
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            if st.button("Sign in", key="login_btn"):
                if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.markdown(
                        '<div class="pill-err">Incorrect username or password.</div>',
                        unsafe_allow_html=True,
                    )
        return

    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;flex-wrap:wrap">
        <div style="font-family:'Caveat',cursive;font-size:28px;font-weight:700;color:#2d2a1e">
            Admin Dashboard
        </div>
        <span class="sticker sticker-green">Logged in</span>
    </div>
    """, unsafe_allow_html=True)

    admin_left, admin_right = st.columns([1, 1.4], gap="large")

    with admin_left:

        st.markdown("""
        <div class="section-label">📁 Create New Event</div>
        """, unsafe_allow_html=True)

        if "new_event_name_val" not in st.session_state:
            st.session_state["new_event_name_val"] = ""

        def _on_event_name_change():
            st.session_state["new_event_name_val"] = st.session_state["new_event_name"]

        new_event_name = st.text_input(
            "Event name",
            placeholder="e.g. Q3 Town Hall, Product Launch ",
            key="new_event_name",
            label_visibility="collapsed",
            on_change=_on_event_name_change,
        )

        create_disabled = len(st.session_state["new_event_name_val"].strip()) == 0

        if st.button(
            "✚  Create Event Folder",
            key="create_event_btn",
            disabled=create_disabled,
        ):
            safe_name = sanitize_folder_name(st.session_state.get("new_event_name", ""))
            created = event_store.create_event(safe_name)
            if not created:
                st.markdown(
                    '<div class="pill-warn">An event with this name already exists.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.session_state.admin_active_event = safe_name
                st.markdown(
                    f'<div class="pill-ok">Event "<strong>{safe_name}</strong>" created and selected!</div>',
                    unsafe_allow_html=True,
                )
                st.rerun()

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        st.markdown(
            "<hr style='border:none;border-top:2px dashed #e8e0cc;margin:4px 0 20px'>",
            unsafe_allow_html=True,
        )

        event_names = event_store.list_events()

        st.markdown(f"""
        <div class="section-label">
            📂 Your Events
            <span class="sticker sticker-gray" style="font-size:11px;margin-left:4px">
                {len(event_names)}
            </span>
        </div>
        """, unsafe_allow_html=True)

        if not event_names:
            st.markdown("""
            <div style="background:#fff4e0;border:2px solid #ffc87a;border-radius:14px;
                        padding:20px;text-align:center;margin-bottom:16px">
                <div style="font-size:28px;margin-bottom:6px">🗂️</div>
                <div style="font-size:13px;color:#b35a00;font-weight:700">
                    No events yet. Create one above!
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            chosen_event_name = st.selectbox(
                "Select event to manage",
                options=event_names,
                index=None,
                key="admin_event_dropdown",
                label_visibility="collapsed",
                placeholder="📋 Select event to manage",
            )

            if chosen_event_name:
                st.session_state.admin_active_event = chosen_event_name

                img_count = event_store.count_photos(chosen_event_name)
                is_active = chosen_event_name == st.session_state.get("admin_active_event", "")
                st.markdown(f"""
                <div style="display:flex;align-items:center;justify-content:space-between;
                            background:#f0fdf4;border:2px solid #9de0af;border-radius:12px;
                            padding:10px 14px;margin:10px 0 14px">
                    <div style="display:flex;align-items:center;gap:8px">
                        <span style="font-size:16px">{"✅" if is_active else "📁"}</span>
                        <div>
                            <div style="font-size:13px;font-weight:800;color:#1e7a3a;
                                        overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
                                        max-width:160px" title="{chosen_event_name}">
                                {chosen_event_name}
                            </div>
                            <div style="font-size:11px;color:#4a9a5a;font-weight:600">
                                {img_count} photo{"s" if img_count != 1 else ""}
                            </div>
                        </div>
                    </div>
                    <span class="sticker sticker-green" style="font-size:10px">Managing</span>
                </div>
                """, unsafe_allow_html=True)

                st.markdown('<div class="admin-del-btn">', unsafe_allow_html=True)
                if st.button(f'🗑  Delete  "{chosen_event_name}"', key=f"del_{chosen_event_name}"):
                    event_store.delete_event(chosen_event_name)
                    clear_embedding_cache()
                    st.session_state.admin_active_event = None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
        if st.button("🚪  Log out", key="logout_btn"):
            st.session_state.admin_logged_in = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with admin_right:
        active_event_name = st.session_state.get("admin_active_event")

        if not active_event_name or not event_store.event_exists(active_event_name):
            st.markdown("""
            <div class="fun-card" style="text-align:center;padding:56px 32px">
                <div style="font-size:56px;margin-bottom:14px">👈</div>
                <div style="font-family:'Caveat',cursive;font-size:26px;font-weight:700;
                            color:#2d2a1e;margin-bottom:10px">Select an event to manage</div>
                <div style="font-size:14px;color:#7a6f55;max-width:340px;margin:0 auto">
                    Create a new event or pick one from the dropdown on the left
                    to upload and manage photos here.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            img_count = event_store.count_photos(active_event_name)

            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;flex-wrap:wrap">
                <span style="font-size:20px">📤</span>
                <div style="font-family:'Caveat',cursive;font-size:22px;font-weight:700;color:#2d2a1e">
                    Uploading to:
                </div>
                <span class="sticker sticker-blue" style="font-size:13px;max-width:260px;
                    overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    {active_event_name}
                </span>
                <span class="sticker sticker-gray">{img_count} photo{"s" if img_count != 1 else ""}</span>
            </div>
            """, unsafe_allow_html=True)

            event_files = st.file_uploader(
                "Select photos to upload",
                type=["jpg", "jpeg", "png", "webp", "bmp"],
                accept_multiple_files=True,
                key=f"uploader_{active_event_name}",
                label_visibility="collapsed",
            )

            if event_files:
                st.caption(f"{len(event_files)} file{'s' if len(event_files) != 1 else ''} selected — ready to upload")

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

            col_up, col_clr, col_cache = st.columns([1.2, 1, 1], gap="small")

            with col_up:
                st.markdown('<div class="upload-btn">', unsafe_allow_html=True)
                upload_clicked = st.button(
                    "⬆  Upload Photos",
                    key=f"upload_btn_{active_event_name}",
                    disabled=not event_files,
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_clr:
                st.markdown('<div class="clear-photos-btn">', unsafe_allow_html=True)
                clear_clicked = st.button(
                    "🗑  Clear All",
                    key=f"clear_photos_{active_event_name}",
                    disabled=img_count == 0,
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_cache:
                st.markdown('<div class="cache-btn">', unsafe_allow_html=True)
                cache_clicked = st.button(
                    "🔄  Clear Cache",
                    key=f"clear_cache_{active_event_name}",
                )
                st.markdown('</div>', unsafe_allow_html=True)

            if upload_clicked and event_files:
                prog = st.progress(0, text="Saving…")
                skipped = []
                for i, f in enumerate(event_files):
                    data = f.read()
                    try:
                        photo_store.save_photo(active_event_name, f.name, data)
                    except InvalidImageError:
                        # File isn't actually a valid image (bad/renamed file) — skip it
                        # instead of letting it crash the matching pipeline later.
                        skipped.append(f.name)
                    prog.progress(
                        (i + 1) / len(event_files),
                        text=f"Saved {i + 1}/{len(event_files)}",
                    )
                prog.empty()
                clear_embedding_cache()
                st.session_state.results = None
                if skipped:
                    st.markdown(
                        f'<div class="pill-warn">Skipped {len(skipped)} invalid file'
                        f'{"s" if len(skipped) != 1 else ""}: {", ".join(skipped)}</div>',
                        unsafe_allow_html=True,
                    )
                st.rerun()

            if clear_clicked:
                photo_store.delete_all_photos(active_event_name)
                clear_embedding_cache()
                st.rerun()

            if cache_clicked:
                clear_embedding_cache()
                st.markdown('<div class="pill-ok" style="margin-top:6px">Cache cleared successfully.</div>', unsafe_allow_html=True)

            refreshed_count = event_store.count_photos(active_event_name)
            pill_class = "pill-ok" if refreshed_count > 0 else "pill-info"
            pill_msg = (
                f"{refreshed_count} photo{'s' if refreshed_count != 1 else ''} in this event — users can search!"
                if refreshed_count > 0
                else "No photos yet — upload some above."
            )
            st.markdown(f'<div class="{pill_class}" style="margin-top:10px">{pill_msg}</div>', unsafe_allow_html=True)

            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="section-label">
                📸 Photos in "{active_event_name}"
            </div>
            """, unsafe_allow_html=True)

            if refreshed_count > 0:
                imgs = photo_store.list_photo_paths(active_event_name)
                pcols = st.columns(4)
                for i, img_path in enumerate(imgs[:20]):
                    with pcols[i % 4]:
                        st.image(
                            Image.open(img_path),
                            use_container_width=True,
                            caption=img_path.name[:14],
                        )
                        st.markdown('<div class="photo-del-btn">', unsafe_allow_html=True)
                        if st.button(
                            "🗑 Remove",
                            key=f"del_photo_{active_event_name}_{img_path.name}",
                        ):
                            photo_store.delete_photo(active_event_name, img_path.name)
                            clear_embedding_cache()
                            st.session_state.results = None
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                if len(imgs) > 20:
                    st.caption(f"… and {len(imgs) - 20} more photos")
            else:
                st.markdown("""
                <div class="fun-card" style="text-align:center;padding:36px">
                    <div style="font-size:40px;margin-bottom:8px">🙏</div>
                    <div style="font-size:15px;color:#7a6f55">No photos uploaded yet.</div>
                </div>
                """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  APP ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
render_header()

if "active_page" not in st.session_state:
    st.session_state.active_page = "user"

nav_col1, nav_col2, nav_spacer = st.columns([1, 1, 6])

with nav_col1:
    css_class = "nav-tab-btn-active" if st.session_state.active_page == "user" else "nav-tab-btn"
    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
    if st.button("Find My Photos", key="nav_user_btn"):
        st.session_state.active_page = "user"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with nav_col2:
    css_class = "nav-tab-btn-active" if st.session_state.active_page == "admin" else "nav-tab-btn"
    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
    if st.button("Admin", key="nav_admin_btn"):
        st.session_state.active_page = "admin"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

if st.session_state.active_page == "user":
    render_user_tab()
else:
    render_admin_tab()
