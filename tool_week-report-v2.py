import streamlit as st
import pandas as pd
import numpy as np
import pymongo
import io

st.set_page_config(page_title="PO-Tracking Tool", layout="wide", page_icon="⚙️")

# --- CẤU HÌNH MONGODB ---
MONGO_URI = "mongodb://admin:123456@192.168.40.168:27017/"
DB_NAME = "po_tracking_db"
COLLECTION_NAME = "daily_reports"

@st.cache_resource
def init_connection():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        return client
    except Exception:
        return None

client = init_connection()

# --- HÀM TÍNH TOÁN ---
def calculate_metrics(df):
    if 'ACT' not in df.columns or 'Target' not in df.columns: return df
    df['EFF'] = df['ACT'] / df['Target']
    df['RFT'] = 1 - (df['Defect'] / df['ACT'])
    df.replace([np.inf, -np.inf], 0, inplace=True)
    numeric_cols = df.select_dtypes(include=['number']).columns
    df.fillna({col: 0 for col in numeric_cols}, inplace=True)
    return df

st.markdown("<h3 style='text-align: center; color: #1E88E5;'>CÔNG TY TNHH LONG VĨ VIỆT NAM - LONGWAY VIETNAM CO., LTD</h3>", unsafe_allow_html=True)
st.title("⚙️ Tool Xử lý Dữ liệu & Lưu Database")

if client is None:
    st.error("🔴 Không thể kết nối tới MongoDB.")
else:
    st.success("🟢 Đã kết nối MongoDB Database")

import datetime

current_week = datetime.date.today().isocalendar()[1]
selected_week = st.number_input("📌 Gán Tuần Báo Cáo cho File này (Sửa nếu cần):", min_value=1, max_value=53, value=current_week)

uploaded_file = st.file_uploader("Tải lên file Excel báo cáo gốc", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'): 
            raw_df = pd.read_csv(uploaded_file)
        else: 
            raw_df = pd.read_excel(uploaded_file, sheet_name='Report')
            
        # Tiền xử lý dữ liệu (giữ nguyên logic của bạn)
        raw_df.columns = raw_df.columns.str.strip()
        raw_df.rename(columns={'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'}, inplace=True)
        
        for col in ['Working', 'Line', 'Date']:
            if col in raw_df.columns:
                raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
                raw_df[col] = raw_df[col].replace(r'[\x00-\x1F\x7F-\x9F]', '', regex=True)
                raw_df[col] = raw_df[col].replace(['nan', ''], '(Trống)')
        
        # Luôn sử dụng Tuần do người dùng chọn tay để đảm bảo tính nhất quán 100%
        raw_df['Week'] = selected_week

        raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
        
        for col in ['Target', 'ACT', 'Defect']:
            if col in raw_df.columns:
                raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

        # Khối lưu Database
        if client is not None:
            st.info("💡 Lưu dữ liệu này vào Hệ thống để hiển thị lên Dashboard")
            if st.button("💾 Lưu Dữ Liệu vào MongoDB", type="primary"):
                db = client[DB_NAME]
                collection = db[COLLECTION_NAME]
                records = raw_df.to_dict(orient='records')
                if len(records) > 0:
                    collection.insert_many(records)
                    st.success(f"✅ Đã lưu thành công {len(records)} dòng dữ liệu vào hệ thống!")
                else:
                    st.warning("Dữ liệu rỗng, không có gì để lưu.")

        # Hiển thị dữ liệu xem trước
        st.subheader("Bảng Dữ liệu đã xử lý (Preview)")
        preview_df = calculate_metrics(raw_df.copy())
        st.dataframe(preview_df.head(50), use_container_width=True)

        # Tạo nút xuất Excel (Bạn có thể chèn lại hàm ghi Excel chi tiết của bạn vào đây)
        # buffer = io.BytesIO()
        # with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        #     preview_df.to_excel(writer, index=False, sheet_name='Data_Processed')
        # st.download_button("Tải file Excel đã xử lý", data=buffer.getvalue(), file_name="Processed_Report.xlsx")

    except Exception as e:
        st.error(f"Lỗi: {e}")