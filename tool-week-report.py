import streamlit as st
from faster_whisper import WhisperModel
import tempfile
import os

st.set_page_config(page_title="Audio Scribe Tool", page_icon="🎙️", layout="centered")

st.title("🎙️ Audio to Timestamped Text (Faster)")
st.markdown("Upload file MP3 và tool sẽ trả về file TXT với định dạng `[MM:SS] Câu nói`.")

# Load model Faster-Whisper (Không dùng Torch, chạy rất nhẹ trên CPU)
@st.cache_resource
def load_model():
    # compute_type="int8" giúp giảm một nửa dung lượng RAM cần dùng
    return WhisperModel("base", device="cpu", compute_type="int8")

model = load_model()

uploaded_file = st.file_uploader("Tải lên file âm thanh", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    st.audio(uploaded_file, format='audio/mp3')
    
    if st.button("🚀 Xử lý âm thanh", use_container_width=True):
        with st.spinner("AI đang nghe và chép chính tả..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_filename = tmp_file.name

            try:
                # Transcribe bằng Faster-Whisper
                segments, info = model.transcribe(tmp_filename, beam_size=5)
                
                formatted_text = ""
                for segment in segments:
                    start_time = segment.start
                    text = segment.text.strip()
                    
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    time_str = f"[{minutes:02d}:{seconds:02d}]"
                    
                    formatted_text += f"{time_str} {text}\n"

                st.success("✅ Đã xử lý xong!")
                st.text_area("Preview Nội dung:", formatted_text, height=300)
                
                st.download_button(
                    label="⬇️ Tải xuống file TXT",
                    data=formatted_text,
                    file_name="transcription.txt",
                    mime="text/plain",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")
            finally:
                if os.path.exists(tmp_filename):
                    os.remove(tmp_filename)