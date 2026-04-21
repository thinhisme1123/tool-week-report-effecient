import streamlit as st
import pandas as pd
import numpy as np
import io
import traceback

st.set_page_config(page_title="Công cụ Xử lý Báo cáo PO-Tracking", layout="wide")
st.title("Công cụ Xử lý Báo cáo PO-Tracking Hàng Tuần")

st.markdown("""
*💡 **Mẹo:** Ấn biểu tượng **⚙️ Settings** ở góc phải -> Chọn **Theme** -> **Light** để nền web chuyển sang màu trắng sáng giúp chụp ảnh nét hơn.*
""")

uploaded_file = st.file_uploader("Tải lên file Excel báo cáo gốc", type=["xlsx", "csv"])

def calculate_metrics(df):
    """Tính toán EFF và RFT theo đúng công thức chuẩn"""
    df['EFF'] = df['ACT'] / df['Target']
    df['RFT'] = 1 - (df['Defect'] / df['ACT'])
    
    df.replace([np.inf, -np.inf], 0, inplace=True)
    df.fillna(0, inplace=True)
    return df

def get_global_totals(raw_df):
    """Tính toán 1 bộ Grand Total dùng chung cho tất cả các bảng"""
    t_target = raw_df['Target'].sum()
    t_act = raw_df['ACT'].sum()
    t_defect = raw_df['Defect'].sum()
    
    t_eff = t_act / t_target if t_target != 0 else 0
    t_rft = 1 - (t_defect / t_act) if t_act != 0 else 0
    
    return {'Target': t_target, 'ACT': t_act, 'Defect': t_defect, 'EFF': t_eff, 'RFT': t_rft}

def add_grand_total(df, group_col, totals):
    """Thêm dòng Grand Total vào cuối DataFrame"""
    row = {group_col: 'Grand Total'}
    row.update(totals)
    df_total = pd.DataFrame([row])
    return pd.concat([df, df_total], ignore_index=True)

def style_dataframe(data, table_type):
    """Hệ thống tô màu Vector cho giao diện Web"""
    styles = pd.DataFrame('', index=data.index, columns=data.columns)
    
    color_green = 'background-color: #B2FBA5; color: #000000; font-weight: 500;'
    color_red = 'background-color: #FFB3BA; color: #000000; font-weight: 500;'
    color_gt = 'background-color: #FFE699; color: #000000; font-weight: bold;'
    
    gt_mask = data.iloc[:, 0] == 'Grand Total'
    valid_mask = ~gt_mask 
    
    if table_type == 1:
        styles.loc[valid_mask & (data['EFF'] > 0.85), 'EFF'] = color_green
        styles.loc[valid_mask & (data['EFF'] < 0.70), 'EFF'] = color_red
        if 'RFT' in data.columns:
            styles.loc[valid_mask & (data['RFT'] < 0.99), 'RFT'] = color_red
            
    elif table_type == 3:
        styles.loc[valid_mask & (data['EFF'] < 0.70), 'EFF'] = color_red
        styles.loc[valid_mask & (data['EFF'] > 1.0), 'EFF'] = color_green
        if 'RFT' in data.columns:
            styles.loc[valid_mask & (data['RFT'] < 0.99), 'RFT'] = color_red
            valid_data = data[valid_mask]
            top_5_idx = valid_data['RFT'].nlargest(5).index
            styles.loc[top_5_idx, 'RFT'] = color_green
            
    elif table_type == 4:
        styles.loc[valid_mask & (data['EFF'] < 0.50), 'EFF'] = color_red
    
    styles.loc[gt_mask, :] = color_gt
    return styles

def write_excel_sheet(writer, workbook, df, sheet_name, table_type):
    """Xuất file Excel an toàn tuyệt đối (Sửa lỗi Crash khi ghi file)"""
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, header=False)
    worksheet = writer.sheets[sheet_name]
    
    # Format
    header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9', 'border': 1, 'font_color': 'black'})
    border_fmt = workbook.add_format({'border': 1}) # Dữ liệu bỏ căn giữa
    num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0'})
    pct_fmt = workbook.add_format({'border': 1, 'num_format': '0.00%'})
    
    gt_text_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'align': 'left'})
    gt_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
    gt_pct_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '0.00%', 'align': 'right'})
    
    green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'border': 1, 'num_format': '0.00%'})
    red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1, 'num_format': '0.00%'})

    # Ghi Header
    for col_num, value in enumerate(df.columns):
        worksheet.write(0, col_num, value, header_fmt)
        
    # Tính trước các vị trí dòng cần tô Xanh cho Top 5 RFT (Bảng 3)
    top_5_positions = []
    if table_type == 3 and 'RFT' in df.columns:
        valid_df = df[df.iloc[:, 0] != 'Grand Total']
        top_5_labels = valid_df['RFT'].nlargest(5).index
        for lbl in top_5_labels:
            try:
                pos = df.index.get_loc(lbl)
                if isinstance(pos, int): top_5_positions.append(pos)
                else: top_5_positions.extend(np.where(pos)[0])
            except: pass

    # Quét dữ liệu 1 lượt duy nhất để ghi format (Tuyệt đối an toàn)
    for row_num in range(len(df)):
        is_gt = (str(df.iloc[row_num, 0]) == 'Grand Total')
        for col_num, col_name in enumerate(df.columns):
            val = df.iloc[row_num, col_num]
            
            # Format cơ bản
            if is_gt:
                if col_num == 0: fmt = gt_text_fmt
                elif col_name in ['Target', 'ACT', 'Defect']: fmt = gt_num_fmt
                else: fmt = gt_pct_fmt
            else:
                if col_name in ['Target', 'ACT', 'Defect']: fmt = num_fmt
                elif col_name in ['EFF', 'RFT']: fmt = pct_fmt
                else: fmt = border_fmt
                    
            # Đè format màu Xanh/Đỏ
            if not is_gt:
                if table_type == 1:
                    if col_name == 'EFF' and val > 0.85: fmt = green_fmt
                    elif col_name == 'EFF' and val < 0.70: fmt = red_fmt
                    elif col_name == 'RFT' and val < 0.99: fmt = red_fmt
                elif table_type == 3:
                    if col_name == 'EFF' and val < 0.70: fmt = red_fmt
                    elif col_name == 'EFF' and val > 1.0: fmt = green_fmt
                    elif col_name == 'RFT':
                        if row_num in top_5_positions: fmt = green_fmt
                        elif val < 0.99: fmt = red_fmt
                elif table_type == 4:
                    if col_name == 'EFF' and val < 0.50: fmt = red_fmt
            
            # Ghi cell an toàn
            if pd.isna(val) or val == np.inf or val == -np.inf: 
                worksheet.write(row_num + 1, col_num, "", fmt)
            else: 
                worksheet.write(row_num + 1, col_num, val, fmt)
    
    worksheet.set_column(0, len(df.columns)-1, 15)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file, sheet_name='Report')
            
        raw_df.columns = raw_df.columns.str.strip()
        raw_df.rename(columns={'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'}, inplace=True)
        
        # --- BỘ LỌC AN TOÀN TUYỆT ĐỐI ---
        # 1. Dọn sạch ký tự ẩn (xuống dòng, khoảng trắng lỗi)
        for col in ['Working', 'Line', 'Date']:
            if col in raw_df.columns:
                raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
                raw_df[col] = raw_df[col].replace(r'[\x00-\x1F\x7F-\x9F]', '', regex=True) # Xóa ký tự vô hình gây lỗi Excel
                raw_df[col] = raw_df[col].replace(['nan', ''], '(Trống)')
        
        # 2. Loại bỏ hoàn toàn B06/B6
        raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
        
        # 3. Chuẩn hóa số liệu
        for col in ['Target', 'ACT', 'Defect']:
            if col in raw_df.columns:
                raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)
        
        st.success("Đã tải dữ liệu thành công! Đang tiến hành xử lý...")

        global_totals = get_global_totals(raw_df)

        # Bảng 1
        df1 = raw_df.groupby('Line', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
        df1 = calculate_metrics(df1)
        df1 = add_grand_total(df1, 'Line', global_totals)
        
        # Bảng 2
        df2 = raw_df.groupby('Date', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
        df2 = calculate_metrics(df2)
        df2['Sort_Date'] = pd.to_datetime(df2['Date'], errors='coerce', dayfirst=True)
        df2 = df2.sort_values(by='Sort_Date', na_position='first').drop(columns=['Sort_Date']).reset_index(drop=True)
        df2 = add_grand_total(df2, 'Date', global_totals)
        
        # Bảng 3
        df3 = raw_df.groupby('Working', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
        df3 = calculate_metrics(df3)
        df3 = df3.sort_values(by='EFF', ascending=True).reset_index(drop=True)
        df3 = add_grand_total(df3, 'Working', global_totals) 
        
        # Bảng 4
        df4 = raw_df.groupby(['Working', 'Line'], dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
        df4 = calculate_metrics(df4)
        df4 = df4.sort_values(by='EFF', ascending=True).reset_index(drop=True)

        format_dict = {'Target': '{:,.0f}', 'ACT': '{:,.0f}', 'Defect': '{:,.0f}', 'EFF': '{:.2%}', 'RFT': '{:.2%}'}
        
        styled_df1 = df1.style.apply(lambda d: style_dataframe(d, 1), axis=None).format(format_dict)
        styled_df2 = df2.style.apply(lambda d: style_dataframe(d, 2), axis=None).format(format_dict)
        styled_df3 = df3.style.apply(lambda d: style_dataframe(d, 3), axis=None).format(format_dict)
        styled_df4 = df4.style.apply(lambda d: style_dataframe(d, 4), axis=None).format(format_dict)

        st.subheader("Bảng 1: Hiệu suất theo Line")
        st.dataframe(styled_df1, use_container_width=True)

        st.subheader("Bảng 2: Hiệu suất theo Ngày")
        st.dataframe(styled_df2, use_container_width=True)

        st.subheader("Bảng 3: Hiệu suất theo Mã hàng (Working)")
        st.dataframe(styled_df3, use_container_width=True)

        st.subheader("Bảng 4: Chi tiết Working và Line")
        st.dataframe(styled_df4, use_container_width=True)

        # Xuất Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
            workbook = writer.book
            write_excel_sheet(writer, workbook, df1, 'Bảng 1', 1)
            write_excel_sheet(writer, workbook, df2, 'Bảng 2', 2)
            write_excel_sheet(writer, workbook, df3, 'Bảng 3', 3)
            write_excel_sheet(writer, workbook, df4, 'Bảng 4', 4)

        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 Tải xuống File Excel báo cáo đã Format",
            data=excel_data,
            file_name="PO-Tracking_Formatted_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        st.error("🚨 Có lỗi xảy ra trong quá trình xử lý/xuất file!")
        st.error(f"Lỗi ngắn gọn: {e}")
        with st.expander("👉 Nhấn vào đây để xem chi tiết lỗi (Gửi ảnh này cho kỹ thuật)"):
            st.code(traceback.format_exc(), language='text')