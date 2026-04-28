import streamlit as st
import pandas as pd
import numpy as np
import pymongo
import io

st.set_page_config(page_title="PO-Tracking Tool v3", layout="wide", page_icon="⚙️")

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

# --- HÀM THÔNG MINH: TÌM DÒNG TIÊU ĐỀ (HEADER) ---
def smart_read_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        # Thử đọc 10 dòng đầu để tìm header
        preview = pd.read_csv(uploaded_file, sep=None, engine='python', nrows=10, header=None)
        uploaded_file.seek(0)
        header_row = 0
        for i, row in preview.iterrows():
            row_str = " ".join(row.astype(str).values).upper()
            if 'ACT' in row_str or 'TARGET' in row_str or 'LINE' in row_str:
                header_row = i
                break
        return pd.read_csv(uploaded_file, sep=None, engine='python', header=header_row)
    else:
        # Đối với file Excel
        excel_data = pd.ExcelFile(uploaded_file)
        # Ưu tiên sheet 'Report' hoặc 'Tổng Quan'
        sheet_name = 'Report' if 'Report' in excel_data.sheet_names else excel_data.sheet_names[0]
        preview = pd.read_excel(uploaded_file, sheet_name=sheet_name, nrows=10, header=None)
        header_row = 0
        for i, row in preview.iterrows():
            row_str = " ".join(row.astype(str).values).upper()
            if 'ACT' in row_str or 'TARGET' in row_str or 'LINE' in row_str:
                header_row = i
                break
        return pd.read_excel(uploaded_file, sheet_name=sheet_name, header=header_row)

st.title("⚙️ Tool Xử lý Dữ liệu & Lưu Database (Bản sửa lỗi)")

if client is None:
    st.error("🔴 Không thể kết nối tới MongoDB. Vui lòng kiểm tra lại Server.")
else:
    st.success("🟢 Đã kết nối MongoDB Database")

# Cấu hình báo cáo
col_setup1, col_setup2 = st.columns([1, 2])
with col_setup1:
    report_week = st.number_input("📅 Báo cáo cho Tuần mấy?", min_value=1, max_value=53, value=15)

uploaded_file = st.file_uploader("Tải lên file báo cáo (CSV hoặc Excel)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        raw_df = smart_read_file(uploaded_file)
        
        # Chuẩn hóa tên cột
        raw_df.columns = raw_df.columns.str.strip()
        rename_map = {
            'Sum of ACT': 'ACT', 'Actual': 'ACT',
            'Sum of Target': 'Target',
            'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'
        }
        raw_df.rename(columns=rename_map, inplace=True)

        # Kiểm tra cột bắt buộc
        required = ['ACT', 'Target', 'Defect', 'Line', 'Date', 'Working']
        missing = [c for c in required if c not in raw_df.columns]

        if missing:
            st.error(f"❌ File thiếu các cột cần thiết: {', '.join(missing)}")
            st.info("💡 Mẹo: Hãy kiểm tra xem file của bạn có các cột ACT, Target, Defect, Line, Date, Working hay không.")
        else:
            # Tiền xử lý dữ liệu sạch
            for col in ['Working', 'Line', 'Date']:
                raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
            
            raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
            
            for col in ['Target', 'ACT', 'Defect']:
                raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

            # Gán số tuần để phân biệt dữ liệu
            raw_df['Week'] = report_week

            # Hiển thị nút lưu
            st.info(f"Dữ liệu Tuần {report_week} đã sẵn sàng. Bạn có muốn lưu vào hệ thống không?")
            if st.button("💾 Xác nhận lưu vào MongoDB", type="primary"):
                db = client[DB_NAME]
                collection = db[COLLECTION_NAME]
                # Xoá dữ liệu cũ của tuần này để tránh trùng lặp
                collection.delete_many({"Week": report_week})
                records = raw_df.to_dict(orient='records')
                collection.insert_many(records)
                st.success(f"✅ Đã lưu thành công dữ liệu Tuần {report_week}!")

            # Preview dữ liệu đã tính toán
            st.subheader("Xem trước kết quả")
            final_df = calculate_metrics(raw_df.copy())
            st.dataframe(final_df, use_container_width=True)

    except Exception as e:
        st.error(f"Lỗi xử lý file: {e}")