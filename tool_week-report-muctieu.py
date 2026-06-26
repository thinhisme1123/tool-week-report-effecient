import streamlit as st
import pandas as pd
import io

# Tiêu đề ứng dụng
st.title("Ứng dụng Xử lý Dữ liệu PO Tracking")
st.write("Tải file dữ liệu lên để tự động tính trung bình % Mục tiêu.")

# Tạo nút upload file
uploaded_file = st.file_uploader("Chọn file CSV hoặc Excel của bạn", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        # Đọc dữ liệu dựa trên định dạng file
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.subheader("Dữ liệu gốc (Xem trước 5 dòng đầu)")
        st.dataframe(df.head())

        # Xử lý dữ liệu
        df_clean = df.dropna(subset=['% Mục tiêu']).copy()
        df_clean['% Mục tiêu Num'] = df_clean['% Mục tiêu'].astype(str).str.replace('%', '').str.replace(',', '').astype(float)
        
        summary_df = df_clean.groupby(['Line', 'Working'])['% Mục tiêu Num'].mean().reset_index()
        summary_df['% Mục tiêu'] = summary_df['% Mục tiêu Num'].apply(lambda x: f"{x:.2f}%")
        
        final_df = summary_df[['Line', 'Working', '% Mục tiêu']]

        st.subheader("Dữ liệu sau khi xử lý")
        st.dataframe(final_df)

        # Chuyển đổi dataframe thành file Excel trong bộ nhớ để tải về
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False, sheet_name='Result')
        
        processed_data = output.getvalue()

        # Tạo nút tải file xuống
        st.download_button(
            label="📥 Tải file đã xử lý xuống (Excel)",
            data=processed_data,
            file_name="Processed_PO_Tracking.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {e}")