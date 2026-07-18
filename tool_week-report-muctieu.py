import streamlit as st
import pandas as pd
import io
import plotly.express as px

# Cài đặt giao diện trang web
st.set_page_config(page_title="PO Tracking Dashboard", layout="wide")

st.title("📈 Ứng dụng Xử lý & Báo cáo PO Tracking")
st.write("Tải file dữ liệu lên để tự động tổng hợp, báo đỏ các mục dưới 70% và xem biểu đồ tổng quan.")

# Hàm tô màu trên giao diện hiển thị bảng Streamlit
def color_under_70(val):
    try:
        num = float(str(val).replace('%', '').replace(',', ''))
        if num < 70:
            return 'background-color: #FFC7CE; color: #9C0006; font-weight: bold;'
    except:
        pass
    return ''

# Tạo khu vực tải file
uploaded_file = st.file_uploader("📂 Chọn file CSV hoặc Excel của bạn", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        # 1. ĐỌC DỮ LIỆU
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # 2. XỬ LÝ DỮ LIỆU
        df_clean = df.dropna(subset=['% Mục tiêu']).copy()
        df_clean['% Mục tiêu Num'] = df_clean['% Mục tiêu'].astype(str).str.replace('%', '').str.replace(',', '').astype(float)
        
        # Gom nhóm và tính trung bình
        summary_df = df_clean.groupby(['Line', 'Working'])['% Mục tiêu Num'].mean().reset_index()
        summary_df['% Mục tiêu Hiển thị'] = summary_df['% Mục tiêu Num'].apply(lambda x: f"{x:.2f}%")
        
        # 3. CHIA GIAO DIỆN THÀNH 2 TAB: DASHBOARD VÀ BẢNG DỮ LIỆU
        tab1, tab2 = st.tabs(["📊 Client Dashboard", "📋 Bảng Dữ Liệu & Tải Xuống"])
        
        with tab1:
            st.subheader("Tổng quan % Mục tiêu")
            
            # Tính toán các chỉ số nhanh (Metrics)
            avg_all = summary_df['% Mục tiêu Num'].mean()
            under_70_count = len(summary_df[summary_df['% Mục tiêu Num'] < 70])
            total_items = len(summary_df)
            
            col1, col2, col3 = st.columns(3)
            col1.metric(label="Trung bình toàn hệ thống", value=f"{avg_all:.2f}%")
            col2.metric(label="Số mã dưới 70%", value=under_70_count, delta="Cần chú ý", delta_color="inverse")
            col3.metric(label="Tổng số mã (Line + Working)", value=total_items)
            
            st.divider()
            
            # Vẽ biểu đồ bằng Plotly
            fig = px.bar(
                summary_df, 
                x="Working", 
                y="% Mục tiêu Num", 
                color="Line",
                title="Biểu đồ % Mục tiêu theo Working và Line",
                labels={"% Mục tiêu Num": "% Mục tiêu", "Working": "Mã Working"},
                text_auto='.2f' # Hiển thị số trên đầu cột
            )
            
            # Thêm đường gạch ngang màu đỏ ở mốc 70%
            fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Mốc 70% Báo động", annotation_position="bottom right")
            
            # Tùy chỉnh giao diện biểu đồ
            fig.update_traces(textposition='outside')
            fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', xaxis_tickangle=-45)
            
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("Dữ liệu chi tiết")
            
            # Chuẩn bị bảng hiển thị trên web
            final_display = summary_df[['Line', 'Working', '% Mục tiêu Hiển thị']].rename(columns={'% Mục tiêu Hiển thị': '% Mục tiêu'})
            styled_df = final_display.style.map(color_under_70, subset=['% Mục tiêu'])
            
            st.dataframe(styled_df, use_container_width=True)

            # Chuẩn bị file Excel để tải về
            df_excel = summary_df.copy()
            df_excel['% Mục tiêu'] = df_excel['% Mục tiêu Num'] / 100.0
            final_excel = df_excel[['Line', 'Working', '% Mục tiêu']]

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_excel.to_excel(writer, index=False, sheet_name='Result')
                
                workbook  = writer.book
                worksheet = writer.sheets['Result']
                
                worksheet.set_column('A:B', 20)
                percent_format = workbook.add_format({'num_format': '0.00%'})
                worksheet.set_column('C:C', 15, percent_format)
                
                red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                total_rows = len(final_excel)
                worksheet.conditional_format(f'C2:C{total_rows + 1}', {
                    'type': 'cell',
                    'criteria': '<',
                    'value': 0.7,
                    'format': red_format
                })
                
            processed_data = output.getvalue()

            st.download_button(
                label="📥 Tải file Excel đã xử lý (Đã tích hợp tô màu tự động)",
                data=processed_data,
                file_name="Processed_PO_Tracking_Dashboard.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {e}")