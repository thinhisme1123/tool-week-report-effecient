import streamlit as st
import pandas as pd
import io
import plotly.express as px
import pymongo
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# --- NẠP BIẾN MÔI TRƯỜNG ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")  
DB_NAME = "po_tracking_db"
COLLECTION_NAME = "weekly_targets"

@st.cache_resource
def init_mongo_connection():
    if not MONGO_URI:
        st.error("Lỗi: Chưa tìm thấy biến môi trường MONGO_URI. Vui lòng kiểm tra lại file .env!")
        return None
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        collection.create_index("created_at", expireAfterSeconds=2419200)
        return collection
    except Exception as e:
        st.error(f"Lỗi kết nối MongoDB: {e}")
        return None

collection = init_mongo_connection()

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Hệ thống Báo cáo & Theo dõi PO", layout="wide")
st.title("📈 Hệ thống Báo cáo & Theo dõi PO Dành Cho Quản Lý")

def color_under_70(val):
    try:
        num = float(str(val).replace('%', '').replace(',', ''))
        if num < 70:
            return 'background-color: #FFC7CE; color: #9C0006; font-weight: bold;'
    except:
        pass
    return ''

def style_pivot(val):
    if pd.isna(val):
        return ''
    try:
        if float(val) < 70:
            return 'background-color: #FFC7CE; color: #9C0006; font-weight: bold;'
    except:
        pass
    return ''

# --- CHIA 3 TAB CHỨC NĂNG ---
tab1, tab2, tab3 = st.tabs(["📊 Phân Tích Dữ Liệu (Manager Dashboard)", "📥 Xử lý & Lưu Dữ Liệu", "📋 Bảng Dữ Liệu Tuần Hiện Tại"])

# ==========================================
# TAB 1: MANAGER DASHBOARD (ĐÃ NÂNG CẤP)
# ==========================================
with tab1:
    st.header("Phân tích Chuyên sâu & So sánh Các tuần")
    if collection is not None:
        if st.button("🔄 Cập nhật Dữ liệu Mới nhất từ Máy chủ"):
            pass # Nút dùng để refresh lại trang
            
        history_data = list(collection.find({}, {"_id": 0}))
        
        if len(history_data) > 0:
            df_history = pd.DataFrame(history_data)
            
            # Xử lý đảm bảo cột Week định dạng chuẩn
            df_history['Week'] = df_history['Week'].astype(str)
            weeks = sorted(df_history['Week'].unique())
            latest_week = weeks[-1]
            
            # 1. THỐNG KÊ TỔNG QUAN (SO SÁNH TUẦN NÀY & TUẦN TRƯỚC)
            st.subheader(f"📌 Chỉ số tuần gần nhất (Tuần {latest_week})")
            
            latest_data = df_history[df_history['Week'] == latest_week]
            latest_avg = latest_data['% Mục tiêu Num'].mean()
            
            delta_str = None
            if len(weeks) > 1:
                prev_week = weeks[-2]
                prev_data = df_history[df_history['Week'] == prev_week]
                prev_avg = prev_data['% Mục tiêu Num'].mean()
                delta = latest_avg - prev_avg
                delta_str = f"{delta:+.2f}% so với Tuần {prev_week}"
            
            # Tìm Line xuất sắc nhất và tệ nhất tuần mới nhất
            line_avg_latest = latest_data.groupby('Line')['% Mục tiêu Num'].mean()
            best_line = line_avg_latest.idxmax()
            worst_line = line_avg_latest.idxmin()
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Trung bình Nhà máy", f"{latest_avg:.2f}%", delta=delta_str)
            col2.metric("Số mã (Working) đang xử lý", len(latest_data))
            col3.metric("Line Hiệu suất Cao nhất", f"{best_line} ({line_avg_latest.max():.1f}%)")
            col4.metric("Line Cần Cải thiện", f"{worst_line} ({line_avg_latest.min():.1f}%)", delta="Cần theo dõi", delta_color="inverse")
            
            st.divider()
            
            # 2. BIỂU ĐỒ XU HƯỚNG THEO TỪNG LINE
            st.subheader("📈 So sánh Xu hướng các Line qua các Tuần")
            trend_line_df = df_history.groupby(['Week', 'Line'])['% Mục tiêu Num'].mean().reset_index()
            
            fig_lines = px.line(
                trend_line_df, 
                x="Week", 
                y="% Mục tiêu Num", 
                color="Line", 
                markers=True,
                title="Sự thay đổi hiệu suất của từng Line",
                labels={"% Mục tiêu Num": "Trung bình % Mục tiêu"}
            )
            fig_lines.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Mốc 70%")
            st.plotly_chart(fig_lines, use_container_width=True)
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                # 3. MA TRẬN ĐỐI CHIẾU
                st.subheader("🧮 Ma trận Hiệu suất (Line vs Tuần)")
                st.write("Bảng tính trung bình % mục tiêu. Các ô < 70% sẽ tự động báo đỏ.")
                pivot_df = df_history.pivot_table(index=['Line', 'Working'], columns='Week', values='% Mục tiêu Num', aggfunc='mean')
                
                # Format hiển thị %
                formatted_pivot = pivot_df.style.format("{:.2f}%", na_rep="-").map(style_pivot)
                st.dataframe(formatted_pivot, use_container_width=True)
                
            with col_right:
                # 4. TOP & BOTTOM CỦA TUẦN MỚI NHẤT
                st.subheader(f"🏆 Top/Bottom Mã hàng (Tuần {latest_week})")
                
                # Sắp xếp để lấy Top 5 và Bottom 5
                sorted_latest = latest_data.sort_values(by='% Mục tiêu Num', ascending=False)
                
                tab_top, tab_bottom = st.tabs(["Top 5 Cao nhất", "Bottom 5 Thấp nhất"])
                with tab_top:
                    top5 = sorted_latest.head(5)[['Line', 'Working', '% Mục tiêu Hiển thị']]
                    st.dataframe(top5, hide_index=True, use_container_width=True)
                with tab_bottom:
                    bottom5 = sorted_latest.tail(5)[['Line', 'Working', '% Mục tiêu Hiển thị']]
                    st.dataframe(bottom5.style.map(color_under_70, subset=['% Mục tiêu Hiển thị']), hide_index=True, use_container_width=True)
                    
        else:
            st.warning("Hệ thống hiện tại chưa có dữ liệu lịch sử nào. Vui lòng tải file lên ở Tab 2.")

# ==========================================
# TAB 2: UPLOAD & LƯU DỮ LIỆU
# ==========================================
with tab2:
    uploaded_file = st.file_uploader("📂 Chọn file CSV hoặc Excel của tuần này", type=['csv', 'xlsx'])

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            df_clean = df.dropna(subset=['% Mục tiêu']).copy()
            df_clean['% Mục tiêu Num'] = df_clean['% Mục tiêu'].astype(str).str.replace('%', '').str.replace(',', '').astype(float)
            
            if 'Week' in df_clean.columns:
                summary_df = df_clean.groupby(['Week', 'Line', 'Working'])['% Mục tiêu Num'].mean().reset_index()
            else:
                summary_df = df_clean.groupby(['Line', 'Working'])['% Mục tiêu Num'].mean().reset_index()
                summary_df['Week'] = 'N/A'
                
            summary_df['% Mục tiêu Hiển thị'] = summary_df['% Mục tiêu Num'].apply(lambda x: f"{x:.2f}%")

            if st.button("💾 Lưu dữ liệu tuần này vào Hệ thống"):
                if collection is not None:
                    records_to_insert = summary_df.to_dict("records")
                    current_time = datetime.now(timezone.utc)
                    for record in records_to_insert:
                        record["created_at"] = current_time
                        
                    collection.insert_many(records_to_insert)
                    st.success("✅ Đã lưu thành công! Hãy sang Tab 1 để xem phân tích.")
                else:
                    st.error("Chưa kết nối được với MongoDB.")
                    
        except Exception as e:
            st.error(f"Lỗi xử lý file: {e}")

# ==========================================
# TAB 3: BẢNG DỮ LIỆU FILE VỪA TẢI LÊN
# ==========================================
with tab3:
    if 'summary_df' in locals():
        final_display = summary_df[['Week', 'Line', 'Working', '% Mục tiêu Hiển thị']].rename(columns={'% Mục tiêu Hiển thị': '% Mục tiêu'})
        styled_df = final_display.style.map(color_under_70, subset=['% Mục tiêu'])
        st.dataframe(styled_df, use_container_width=True)

        df_excel = summary_df.copy()
        df_excel['% Mục tiêu'] = df_excel['% Mục tiêu Num'] / 100.0
        final_excel = df_excel[['Week', 'Line', 'Working', '% Mục tiêu']]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_excel.to_excel(writer, index=False, sheet_name='Result')
            workbook  = writer.book
            worksheet = writer.sheets['Result']
            
            worksheet.set_column('A:C', 15)
            percent_format = workbook.add_format({'num_format': '0.00%'})
            worksheet.set_column('D:D', 15, percent_format)
            
            red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            total_rows = len(final_excel)
            worksheet.conditional_format(f'D2:D{total_rows + 1}', {
                'type': 'cell',
                'criteria': '<',
                'value': 0.7,
                'format': red_format
            })
            
        processed_data = output.getvalue()
        st.download_button(
            label="📥 Tải file Excel của tuần này",
            data=processed_data,
            file_name="Processed_PO_Tracking_Current.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Vui lòng tải file lên ở Tab 2 trước.")