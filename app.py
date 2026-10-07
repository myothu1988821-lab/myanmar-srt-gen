import re, subprocess, tempfile, io
from pathlib import Path
import streamlit as st
import imageio_ffmpeg

st.set_page_config(page_title="Video → SRT (AI Narration)", page_icon="🎬")
CSS = """<style>
.stApp{background:linear-gradient(135deg,#0f2027 0%,#203a43 55%,#2c5364 100%)}
.stApp h1{background:linear-gradient(90deg,#7fe7dc,#ffd76e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:800}
.stApp p,.stApp label,.stMarkdown{color:#eaf6f6!important}
div.stButton>button{background:linear-gradient(90deg,#00bfa5,#00acc1);color:#fff;border:none;border-radius:12px;padding:.6rem 2rem;font-size:1.1rem;font-weight:700;width:100%}
div[data-testid="stTextArea"] textarea{background-color:#16323c!important;color:#fff!important;border-radius:12px}
div[data-testid="stTextInput"] input{background-color:#16323c!important;color:#fff!important;border-radius:12px}
section[data-testid="stFileUploader"]{background:rgba(255,255,255,.06);border-radius:14px;padding:1rem;border:1px dashed rgba(255,255,255,.3)}
header[data-testid="stHeader"]{background:rgba(0,0,0,0)}
footer{visibility:hidden}
</style>"""
st.markdown(CSS, unsafe_allow_html=True)
st.title("🎬 Video → SRT (AI Narration)")
st.markdown("Video တင်လိုက်ရုံနဲ့ AI က ကြည့်ပြီး <b>မြန်မာ narration SRT</b> ရေးပေးမယ်", unsafe_allow_html=True)
st.caption("🔖 v2026-10-07-gemini")
st.write("")

ff = imageio_ffmpeg.get_ffmpeg_exe()

with st.expander("🔑 Gemini API Key (အခမဲ့) — ဘယ်လိုယူရမလဲ", expanded=False):
    st.markdown("""
    1. [aistudio.google.com](https://aistudio.google.com) ကို သွားပါ (Google account နဲ့ login)
    2. **Get API Key** → **Create API Key** နှိပ်ပါ
    3. Key ကို copy ကူးပြီး အောက်မှာ ထည့်ပါ
    - ကတ်မလို၊ အခမဲ့ပါ ✅
    """)

api_key = st.text_input("Gemini API Key", type="password", placeholder="AIza...")
v = st.file_uploader("Video တင်ပါ", type=["mp4", "mov", "mkv", "webm"])

style = st.selectbox("Narration ပုံစံ", [
    "ဇာတ်လမ်း ဇာတ်ပြောသံ (dramatic)",
    "ရိုးရိုး ရှင်းပြချက် (simple)",
    "ကလေးအတွက် ပုံပြင် (kids story)",
])

if st.button("📝 SRT ထုတ်မယ်", type="primary"):
    if not api_key.strip():
        st.error("API Key ထည့်ပေးပါ။"); st.stop()
    if not v:
        st.error("Video တင်ပေးပါ။"); st.stop()

    tmp = Path(tempfile.mkdtemp())
    vp = tmp / "input.mp4"
    vp.write_bytes(v.getvalue())

    # video duration
    pr = subprocess.run([ff, "-hide_banner", "-i", str(vp)],
                        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", pr.stderr)
    if not m:
        st.error("Video duration ဖတ်မရဘူး"); st.stop()
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    st.info(f"⏱️ Video ကြာချိန်: {dur:.0f} စက္ကန့်")

    # extract frames: aim ~45 frames max (supports up to 15+ min video)
    nframes = min(45, max(6, int(dur // 20)))
    step = dur / nframes
    st.info(f"🖼️ Frame {nframes} ခု ထုတ်နေတယ်...")
    frames = []
    for i in range(nframes):
        ts = i * step
        fp = tmp / f"f{i:02d}.jpg"
        subprocess.run([ff, "-hide_banner", "-y", "-v", "error",
                        "-ss", f"{ts:.1f}", "-i", str(vp),
                        "-frames:v", "1", "-q:v", "5",
                        "-vf", "scale=480:-1", str(fp)],
                       check=True, stdin=subprocess.DEVNULL)
        frames.append((ts, fp))

    # call Gemini
    with st.spinner("🤖 AI က video ကြည့်ပြီး narration ရေးနေတယ်... (ခဏစောင့်ပါ)"):
        try:
            import google.generativeai as genai
            from PIL import Image
        except ImportError:
            st.error("google-generativeai / Pillow မရှိဘူး — requirements.txt စစ်ပါ"); st.stop()

        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel("gemini-2.0-flash")

        desc = "\n".join(f"- {ts:.0f}s" for ts, _ in frames)
        prompt = f"""You are a Burmese story narrator. I will show you {nframes} frames from a video (total duration {dur:.0f} seconds).

Frame timestamps (seconds):
{desc}

Watch the frames in order and write a dramatic Burmese narration SRT file covering the whole video from 0 to {dur:.0f} seconds.

Rules:
- Output ONLY valid SRT format, no explanations
- Segments must be continuous with NO gaps (each end time = next start time)
- Each segment 5-8 seconds long
- Write in natural, emotional Burmese narrator style (like a storyteller)
- Describe what happens, build drama, end with a moral/lesson
- Use correct Myanmar Unicode spelling
- Format:
1
00:00:00,000 --> 00:00:07,000
(narration text here)

Style: {style}
"""

        parts = [prompt]
        for ts, fp in frames:
            parts.append(f"[Frame at {ts:.0f}s]")
            parts.append(Image.open(fp))

        try:
            resp = model.generate_content(parts, request_options={"timeout": 300})
            srt_text = resp.text.strip()
        except Exception as e:
            st.error(f"Gemini API error: {e}"); st.stop()

    # clean up code fences if present
    srt_text = re.sub(r"^```\w*\n?", "", srt_text)
    srt_text = re.sub(r"\n?```$", "", srt_text).strip()

    # validate basic SRT structure
    nsegs = len(re.findall(r"^\d+\s*$", srt_text, re.M))
    if nsegs < 3 or "-->" not in srt_text:
        st.error("AI က SRT format မမှန်တာ ပြန်ပေးတယ် — ထပ်နှိပ်ကြည့်ပါ")
        with st.expander("AI ပြန်ပေးတာ ကြည့်မယ်"):
            st.code(srt_text[:2000])
        st.stop()

    st.success(f"ရပြီ! 🎉 (အပိုင်း {nsegs} ပိုင်း)")
    st.text_area("SRT output", srt_text, height=300)
    st.download_button("⬇️ SRT download ဆွဲမယ်", srt_text.encode("utf-8"),
                       file_name="narration.srt", mime="text/plain")
    st.caption("💡 ဒီ SRT ကို Dubbing site မှာ သုံးပြီး အသံထုတ်လို့ရတယ်")
