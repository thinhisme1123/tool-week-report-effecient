import streamlit as st
import pandas as pd
import io

st.title("Công Cụ Xử Lý Báo Cáo PO Tracking")

# Upload file
uploaded_file = st.file_uploader("Tải lên file Report (CSV hoặc Excel)", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        # Đọc dữ liệu
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, sheet_name='Report')
            
        # SỬA LỖI TẠI ĐÂY: Xóa khoảng trắng tên cột
        df.columns = df.columns.str.strip()
        
        st.write("Dữ liệu gốc (Report):")
        st.dataframe(df.head())
        # ... (các phần code phía sau giữ nguyên)
        
        # Xử lý dữ liệu
        if '% Mục tiêu' in df.columns:
            # Chuyển đổi an toàn sang kiểu số, xử lý cả trường hợp có dấu '%' hoặc chuỗi không hợp lệ
            df['% Mục tiêu'] = pd.to_numeric(
                df['% Mục tiêu'].astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False).str.strip(), 
                errors='coerce'
            )

            summary_df = df.groupby(['Line', 'Working'])['% Mục tiêu'].mean().reset_index()
            summary_df['% Mục tiêu'] = summary_df['% Mục tiêu'].round(2)
            
            st.write("Dữ liệu sau khi xử lý (Line Working Summary):")
            st.dataframe(summary_df)
            
            # Cho phép tải file về
            csv = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Tải file kết quả (CSV)",
                data=csv,
                file_name='Line_Working_Summary_Output.csv',
                mime='text/csv',
            )
        else:
            st.error("Không tìm thấy cột '% Mục tiêu' trong file dữ liệu.")
            
    except Exception as e:
        st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {e}")