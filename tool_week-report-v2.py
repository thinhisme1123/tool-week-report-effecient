import streamlit as st
import pandas as pd
import numpy as np
import pymongo
import plotly.express as px
import plotly.graph_objects as go
import io
import os
import datetime
from dotenv import load_dotenv

# Tải biến môi trường từ file .env
load_dotenv()

st.set_page_config(page_title="Hệ thống Quản lý PO-Tracking", layout="wide", page_icon="📈")

# --- CẤU HÌNH MONGODB TỪ BIẾN MÔI TRƯỜNG ---
# Khai báo an toàn bằng os.getenv để tránh lỗi unhashable dict của Streamlit
MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:123456@192.168.40.168:27017/")
DB_NAME = os.getenv("DB_NAME", "po_tracking_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "daily_reports")

@st.cache_resource(ttl=60)
def init_connection(uri):
    """Truyền URI làm tham số để Streamlit lưu cache chuỗi an toàn tuyệt đối"""
    if not uri:
        return None
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client
    except Exception:
        return None

client = init_connection(MONGO_URI)

# --- HÀM TÍNH TOÁN CƠ BẢN ---
def calculate_metrics(df):
    if 'ACT' not in df.columns or 'Target' not in df.columns: return df
    df['EFF'] = df['ACT'] / df['Target']
    df['RFT'] = 1 - (df['Defect'] / df['ACT'])
    df.replace([np.inf, -np.inf], 0, inplace=True)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)
    return df

def get_global_totals(raw_df):
    t_target = raw_df['Target'].sum()
    t_act = raw_df['ACT'].sum()
    t_defect = raw_df['Defect'].sum()
    t_eff = t_act / t_target if t_target != 0 else 0
    t_rft = 1 - (t_defect / t_act) if t_act != 0 else 0
    return {'Target': t_target, 'ACT': t_act, 'Defect': t_defect, 'EFF': t_eff, 'RFT': t_rft}

def add_grand_total(df, group_col, totals):
    row = {group_col: 'Grand Total'}
    row.update(totals)
    df_total = pd.DataFrame([row])
    return pd.concat([df, df_total], ignore_index=True)

def style_dataframe(data, table_type):
    styles = pd.DataFrame('', index=data.index, columns=data.columns)
    color_green = 'background-color: #B2FBA5; color: #000; font-weight: 500;'
    color_red = 'background-color: #FFB3BA; color: #000; font-weight: 500;'
    color_gt = 'background-color: #FFE699; color: #000; font-weight: bold;'
    
    gt_mask = data.iloc[:, 0] == 'Grand Total'
    valid_mask = ~gt_mask 
    
    if table_type == 1:
        styles.loc[valid_mask & (data['EFF'] > 0.85), 'EFF'] = color_green
        styles.loc[valid_mask & (data['EFF'] < 0.70), 'EFF'] = color_red
        if 'RFT' in data.columns: styles.loc[valid_mask & (data['RFT'] < 0.99), 'RFT'] = color_red
    elif table_type == 3:
        styles.loc[valid_mask & (data['EFF'] < 0.70), 'EFF'] = color_red
        styles.loc[valid_mask & (data['EFF'] > 1.0), 'EFF'] = color_green
        if 'RFT' in data.columns:
            styles.loc[valid_mask & (data['RFT'] < 0.99), 'RFT'] = color_red
            top_5_idx = data[valid_mask]['RFT'].nlargest(5).index
            styles.loc[top_5_idx, 'RFT'] = color_green
    elif table_type == 4:
        styles.loc[valid_mask & (data['EFF'] < 0.50), 'EFF'] = color_red
    
    styles.loc[gt_mask, :] = color_gt
    return styles

def write_excel_sheet(writer, workbook, df, sheet_name, table_type):
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, header=False)
    worksheet = writer.sheets[sheet_name]
    
    header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9', 'border': 1, 'font_color': 'black'})
    border_fmt = workbook.add_format({'border': 1})
    num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0'})
    pct_fmt = workbook.add_format({'border': 1, 'num_format': '0.00%'})
    
    gt_text_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'align': 'left'})
    gt_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
    gt_pct_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '0.00%', 'align': 'right'})
    
    green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'border': 1, 'num_format': '0.00%'})
    red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1, 'num_format': '0.00%'})

    for col_num, value in enumerate(df.columns):
        worksheet.write(0, col_num, value, header_fmt)
        
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

    for row_num in range(len(df)):
        is_gt = (str(df.iloc[row_num, 0]) == 'Grand Total')
        for col_num, col_name in enumerate(df.columns):
            val = df.iloc[row_num, col_num]
            
            if is_gt:
                if col_num == 0: fmt = gt_text_fmt
                elif col_name in ['Target', 'ACT', 'Defect']: fmt = gt_num_fmt
                else: fmt = gt_pct_fmt
            else:
                if col_name in ['Target', 'ACT', 'Defect']: fmt = num_fmt
                elif col_name in ['EFF', 'RFT']: fmt = pct_fmt
                else: fmt = border_fmt
                    
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
            
            if pd.isna(val) or val == np.inf or val == -np.inf: 
                worksheet.write(row_num + 1, col_num, "", fmt)
            else: 
                worksheet.write(row_num + 1, col_num, val, fmt)
    
    worksheet.set_column(0, len(df.columns)-1, 15)

# --- CÁC HÀM TẠO PIVOT TUẦN (MENU 3) ---
def create_weekly_pivot(df, index_cols):
    dates = sorted(df['Date'].unique())
    frames = []
    
    for d in dates:
        temp = df[df['Date'] == d].groupby(index_cols)[['Target', 'ACT', 'Defect']].sum()
        temp['EFF'] = temp['ACT'] / temp['Target']
        temp['RFT'] = 1 - (temp['Defect'] / temp['ACT'])
        temp.replace([np.inf, -np.inf], 0, inplace=True)
        temp.fillna(0, inplace=True)
        temp.columns = pd.MultiIndex.from_product([[d], temp.columns])
        frames.append(temp)
        
    gt = df.groupby(index_cols)[['Target', 'ACT', 'Defect']].sum()
    gt['EFF'] = gt['ACT'] / gt['Target']
    gt['RFT'] = 1 - (gt['Defect'] / gt['ACT'])
    gt.replace([np.inf, -np.inf], 0, inplace=True)
    gt.fillna(0, inplace=True)
    gt.columns = pd.MultiIndex.from_product([['Grand Total'], gt.columns])
    frames.append(gt)
    
    result = pd.concat(frames, axis=1).fillna(0)
    
    total_df = pd.DataFrame(columns=result.columns, index=['Grand Total'])
    for col_top in result.columns.levels[0]:
        t_tar = result[(col_top, 'Target')].sum()
        t_act = result[(col_top, 'ACT')].sum()
        t_def = result[(col_top, 'Defect')].sum()
        t_eff = t_act / t_tar if t_tar != 0 else 0
        t_rft = 1 - (t_def / t_act) if t_act != 0 else 0
        
        total_df.loc['Grand Total', (col_top, 'Target')] = t_tar
        total_df.loc['Grand Total', (col_top, 'ACT')] = t_act
        total_df.loc['Grand Total', (col_top, 'Defect')] = t_def
        total_df.loc['Grand Total', (col_top, 'EFF')] = t_eff
        total_df.loc['Grand Total', (col_top, 'RFT')] = t_rft
        
    result = pd.concat([result, total_df])
    return result

# --- CÁC HÀM XỬ LÝ CHO MENU 4: LINE_WORKING_SUMMARY CHUẨN ---
def create_line_working_summary(df):
    summary = df.groupby(['Line', 'Working'])[['Target', 'ACT', 'Defect']].sum().reset_index()
    summary = calculate_metrics(summary)
    summary = summary.sort_values(by=['Line', 'Working']).reset_index(drop=True)

    gt_target = summary['Target'].sum()
    gt_act = summary['ACT'].sum()
    gt_defect = summary['Defect'].sum()
    gt_eff = gt_act / gt_target if gt_target != 0 else 0
    gt_rft = 1 - (gt_defect / gt_act) if gt_act != 0 else 0

    gt_row = pd.DataFrame([{
        'Line': 'Grand Total',
        'Working': '',
        'Target': gt_target,
        'ACT': gt_act,
        'Defect': gt_defect,
        'EFF': gt_eff,
        'RFT': gt_rft
    }])

    return pd.concat([summary, gt_row], ignore_index=True)

def write_summary_excel(writer, workbook, df, sheet_name):
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, header=False)
    worksheet = writer.sheets[sheet_name]
    
    header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9', 'border': 1, 'font_color': 'black'})
    border_fmt = workbook.add_format({'border': 1})
    num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0'})
    pct_fmt = workbook.add_format({'border': 1, 'num_format': '0.00%'})
    
    gt_text_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'align': 'left'})
    gt_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '#,##0', 'align': 'right'})
    gt_pct_fmt = workbook.add_format({'bold': True, 'bg_color': '#FFE699', 'border': 1, 'num_format': '0.00%', 'align': 'right'})
    
    green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'border': 1, 'num_format': '0.00%'})
    red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1, 'num_format': '0.00%'})

    for col_num, value in enumerate(df.columns):
        worksheet.write(0, col_num, value, header_fmt)

    for row_num in range(len(df)):
        is_gt = (str(df.iloc[row_num, 0]) == 'Grand Total')
        
        for col_num, col_name in enumerate(df.columns):
            val = df.iloc[row_num, col_num]
            
            if is_gt:
                fmt = gt_text_fmt if col_num <= 1 else (gt_num_fmt if col_name in ['Target', 'ACT', 'Defect'] else gt_pct_fmt)
            else:
                fmt = border_fmt if col_num <= 1 else (num_fmt if col_name in ['Target', 'ACT', 'Defect'] else pct_fmt)
                
            if not is_gt:
                if col_name == 'EFF' and val > 0.85: fmt = green_fmt
                elif col_name == 'EFF' and val < 0.70: fmt = red_fmt
                elif col_name == 'RFT' and val < 0.99: fmt = red_fmt
            
            if pd.isna(val) or val == np.inf or val == -np.inf: 
                worksheet.write(row_num + 1, col_num, "", fmt)
            else: 
                worksheet.write(row_num + 1, col_num, val, fmt)
    
    worksheet.set_column(0, 1, 15)
    worksheet.set_column(2, len(df.columns)-1, 12)

# --- BẢNG ĐIỀU KHIỂN QUẢN TRỊ VIÊN (ADMIN PANEL) ---
if client is not None:
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    with st.sidebar.expander("⚙️ QUẢN TRỊ DATABASE (XÓA DỮ LIỆU)"):
        st.error("⚠️ Cẩn thận: Dữ liệu đã xóa không thể khôi phục!")
        
        all_admin_data = list(collection.find({}, {"_id": 1, "Date": 1}))
        
        if all_admin_data:
            df_admin = pd.DataFrame(all_admin_data)
            df_admin['Date_dt'] = pd.to_datetime(df_admin['Date'], dayfirst=True, errors='coerce')
            df_admin['Week'] = df_admin['Date_dt'].dt.isocalendar().week.fillna(-1).astype(int)
            
            available_admin_weeks = sorted([w for w in df_admin['Week'].unique() if w != -1])
            
            if available_admin_weeks:
                st.markdown("**1. Xóa theo Tuần:**")
                del_week = st.selectbox("Chọn tuần cần xóa:", available_admin_weeks, key='del_week')
                confirm_del = st.checkbox(f"Tôi chắc chắn muốn xóa Tuần {del_week}", key='chk_del')
                if st.button("🗑️ Xóa Tuần Này", disabled=not confirm_del, type="primary"):
                    ids_to_del = df_admin[df_admin['Week'] == del_week]['_id'].tolist()
                    if ids_to_del:
                        collection.delete_many({"_id": {"$in": ids_to_del}})
                        st.success(f"Đã xóa thành công Tuần {del_week}!")
                        st.rerun()
                
                st.divider()
                
                st.markdown("**2. Dọn dẹp dữ liệu cũ:**")
                st.caption("Tính từ ngày mới nhất có trong DB, xóa toàn bộ dữ liệu cách đây hơn 28 ngày (4 tuần).")
                confirm_auto = st.checkbox("Xác nhận dọn dẹp", key='chk_auto')
                if st.button("🧹 Xóa Dữ Liệu Cũ Hơn 4 Tuần", disabled=not confirm_auto):
                    max_date = df_admin['Date_dt'].max()
                    cutoff_date = max_date - pd.Timedelta(days=28)
                    ids_to_clean = df_admin[df_admin['Date_dt'] < cutoff_date]['_id'].tolist()
                    
                    if ids_to_clean:
                        collection.delete_many({"_id": {"$in": ids_to_clean}})
                        st.success(f"Đã dọn dẹp {len(ids_to_clean)} dòng dữ liệu quá hạn!")
                        st.rerun()
                    else:
                        st.info("Không có dữ liệu nào cũ hơn 4 tuần để xóa.")
        else:
            st.info("Database đang trống.")

# ==========================================
# GIAO DIỆN MENU VÀ CÀI ĐẶT TỰ ĐỘNG
# ==========================================
st.sidebar.markdown("### 📅 CÀI ĐẶT BÁO CÁO")
current_week = datetime.datetime.now().isocalendar()[1]
default_report_week = current_week - 1 if current_week > 1 else 52
report_week = st.sidebar.number_input("Số tuần của báo cáo:", min_value=1, max_value=53, value=default_report_week)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎛️ MENU ĐIỀU HƯỚNG")
menu = st.sidebar.radio("Chọn chức năng:", [
    "1. Báo cáo Chuẩn & Lưu Dữ liệu", 
    "2. Dashboard Thống Kê Tổng Quan",
    "3. Xuất Báo Cáo Tuần (Pivot Matrix)",
    "4. Xuất Báo Cáo Line & Working Summary"
])

if client is None: st.sidebar.error("🔴 Không thể kết nối MongoDB. (Kiểm tra lại .env file)")
else: st.sidebar.success("🟢 Đã kết nối MongoDB.")


# ==========================================
# 4. CHỨC NĂNG: LINE_WORKING_SUMMARY
# ==========================================
if menu == "4. Xuất Báo Cáo Line & Working Summary":
    st.title(f"📑 Báo Cáo Chuẩn: Line Working Summary (Tuần {report_week})")
    st.markdown("Tính năng này tạo tệp dữ liệu Data Table siêu sạch, **gộp theo Line rồi đến Working**.")
    
    uploaded_file = st.file_uploader("Tải lên file dữ liệu thô (PO-Tracking Report)", type=["xlsx", "csv"], key="lineworking")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'): raw_df = pd.read_csv(uploaded_file)
            else: raw_df = pd.read_excel(uploaded_file, sheet_name='Report')
                
            raw_df.columns = raw_df.columns.str.strip()
            raw_df.rename(columns={'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'}, inplace=True)
            for col in ['Working', 'Line', 'Date']:
                if col in raw_df.columns:
                    raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
                    raw_df[col] = raw_df[col].replace(r'[\x00-\x1F\x7F-\x9F]', '', regex=True)
                    raw_df[col] = raw_df[col].replace(['nan', ''], '(Trống)')
            raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
            for col in ['Target', 'ACT', 'Defect']:
                if col in raw_df.columns:
                    raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

            st.success("Đã phân tích dữ liệu. Bảng xem trước ở bên dưới:")
            
            df_summary = create_line_working_summary(raw_df)
            
            def style_summary_web(data):
                styles = pd.DataFrame('', index=data.index, columns=data.columns)
                color_green = 'background-color: #B2FBA5; color: #000;'
                color_red = 'background-color: #FFB3BA; color: #000;'
                color_gt = 'background-color: #FFE699; font-weight: bold;'
                
                for i in range(len(data)):
                    if data.iloc[i, 0] == 'Grand Total':
                        styles.iloc[i, :] = color_gt
                    else:
                        if data.loc[i, 'EFF'] > 0.85: styles.loc[i, 'EFF'] = color_green
                        if data.loc[i, 'EFF'] < 0.70: styles.loc[i, 'EFF'] = color_red
                        if data.loc[i, 'RFT'] < 0.99: styles.loc[i, 'RFT'] = color_red
                return styles

            format_dict = {'Target': '{:,.0f}', 'ACT': '{:,.0f}', 'Defect': '{:,.0f}', 'EFF': '{:.2%}', 'RFT': '{:.2%}'}
            styled_summary = df_summary.style.apply(style_summary_web, axis=None).format(format_dict)
            
            st.dataframe(styled_summary, use_container_width=True)
            
            output_sum = io.BytesIO()
            with pd.ExcelWriter(output_sum, engine='xlsxwriter') as writer:
                workbook = writer.book
                write_summary_excel(writer, workbook, df_summary, 'Line_Working_Summary')

            excel_sum_data = output_sum.getvalue()
            
            st.download_button(
                label=f"📥 TẢI XUỐNG FILE LINE WORKING SUMMARY (TUẦN {report_week})",
                data=excel_sum_data,
                file_name=f"PO-Tracking_Line_Working_Summary_Week_{report_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        except Exception as e:
            st.error(f"Lỗi: {e}")

# ==========================================
# 1. BÁO CÁO CHUẨN & LƯU DỮ LIỆU
# ==========================================
elif menu == "1. Báo cáo Chuẩn & Lưu Dữ liệu":
    st.title(f"Báo cáo Bảng PO-Tracking Hàng Tuần (Tuần {report_week})")
    uploaded_file = st.file_uploader("Tải lên file Excel báo cáo gốc", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'): raw_df = pd.read_csv(uploaded_file)
            else: raw_df = pd.read_excel(uploaded_file, sheet_name='Report')
                
            raw_df.columns = raw_df.columns.str.strip()
            raw_df.rename(columns={'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'}, inplace=True)
            
            for col in ['Working', 'Line', 'Date']:
                if col in raw_df.columns:
                    raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
                    raw_df[col] = raw_df[col].replace(r'[\x00-\x1F\x7F-\x9F]', '', regex=True)
                    raw_df[col] = raw_df[col].replace(['nan', ''], '(Trống)')
            
            raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
            
            for col in ['Target', 'ACT', 'Defect']:
                if col in raw_df.columns:
                    raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

            if client is not None:
                st.info("💡 Bạn có muốn lưu dữ liệu này vào Hệ thống Database để lên Dashboard không?")
                if st.button("💾 Lưu Dữ Liệu vào MongoDB", type="primary"):
                    db = client[DB_NAME]
                    collection = db[COLLECTION_NAME]
                    records = raw_df.to_dict(orient='records')
                    if len(records) > 0:
                        collection.insert_many(records)
                        st.success(f"✅ Đã lưu thành công {len(records)} dòng dữ liệu vào hệ thống!")
                    else:
                        st.warning("Dữ liệu rỗng, không có gì để lưu.")

            st.success("Dữ liệu file đã sẵn sàng. Xem báo cáo bên dưới:")
            
            global_totals = get_global_totals(raw_df)

            df1 = raw_df.groupby('Line', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df1 = calculate_metrics(df1)
            df1 = add_grand_total(df1, 'Line', global_totals)
            
            df2 = raw_df.groupby('Date', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df2 = calculate_metrics(df2)
            df2['Sort_Date'] = pd.to_datetime(df2['Date'], errors='coerce', dayfirst=True)
            df2 = df2.sort_values(by='Sort_Date', na_position='first').drop(columns=['Sort_Date']).reset_index(drop=True)
            df2 = add_grand_total(df2, 'Date', global_totals)
            
            df3 = raw_df.groupby('Working', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df3 = calculate_metrics(df3)
            df3 = df3.sort_values(by='EFF', ascending=True).reset_index(drop=True)
            df3 = add_grand_total(df3, 'Working', global_totals) 
            
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

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                workbook = writer.book
                write_excel_sheet(writer, workbook, df1, 'Bảng 1', 1)
                write_excel_sheet(writer, workbook, df2, 'Bảng 2', 2)
                write_excel_sheet(writer, workbook, df3, 'Bảng 3', 3)
                write_excel_sheet(writer, workbook, df4, 'Bảng 4', 4)

            excel_data = output.getvalue()
            
            st.download_button(
                label=f"📥 Tải xuống File Excel báo cáo đã Format (Tuần {report_week})",
                data=excel_data,
                file_name=f"PO-Tracking_Formatted_Report_Week_{report_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"Lỗi: {e}")

# ==========================================
# 2. DASHBOARD THỐNG KÊ
# ==========================================
elif menu == "2. Dashboard Thống Kê Tổng Quan":
    st.title("📈 Dashboard Hiệu Suất Tổng Quan (EFF & RFT)")
    
    if client is None:
        st.error("🔴 Không thể kết nối Database để tải Dashboard. Vui lòng kiểm tra Server MongoDB.")
    else:
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        data_from_db = list(collection.find({}, {'_id': 0}))
        
        if len(data_from_db) == 0:
            st.warning("Hệ thống chưa có dữ liệu. Vui lòng sử dụng Tool Xử lý để tải file lên trước.")
        else:
            df = pd.DataFrame(data_from_db)
            
            if 'Week' not in df.columns:
                date_calc = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
                df['Week'] = date_calc.dt.isocalendar().week.astype(float).fillna(-1).astype(int)
            
            available_weeks = sorted([int(w) for w in df['Week'].unique() if w != -1])
            if available_weeks:
                default_index = len(available_weeks) - 1
                if report_week in available_weeks:
                    default_index = available_weeks.index(report_week)

                st.markdown("### 🗓️ Lọc Dữ Liệu Theo Tuần")
                col_w1, col_w2 = st.columns([1, 4])
                with col_w1:
                    selected_week = st.selectbox("Chọn Tuần", available_weeks, index=default_index)
                with col_w2:
                    st.write("")
                    st.write("")
                    st.info(f"Đang hiển thị báo cáo của **Tuần {selected_week}**.")
                
                df = df[df['Week'] == selected_week].copy()

            df = calculate_metrics(df)
            
            total_target = df['Target'].sum()
            total_act = df['ACT'].sum()
            total_defect = df['Defect'].sum()
            avg_eff = total_act / total_target if total_target > 0 else 0
            avg_rft = 1 - (total_defect / total_act) if total_act > 0 else 0

            st.markdown("### 🎯 Chỉ Số Trọng Yếu")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🎯 Tổng Target", f"{total_target:,.0f}")
            col2.metric("✅ Tổng ACT", f"{total_act:,.0f}")
            col3.metric("⚡ Hiệu Suất (EFF)", f"{avg_eff * 100:.2f}%", delta="Đạt Mức Đỏ" if avg_eff < 0.70 else "Tốt")
            col4.metric("🛠️ Lỗi (RFT)", f"{avg_rft * 100:.2f}%", delta="Nguy Hiểm" if avg_rft < 0.99 else "An Toàn", delta_color="inverse")

            st.divider()

            st.markdown("### 📅 Xu hướng Hiệu suất theo Thời gian")
            df_date = df.groupby('Date')[['Target', 'ACT', 'Defect']].sum().reset_index()
            df_date = calculate_metrics(df_date)
            df_date['Date'] = pd.to_datetime(df_date['Date'], dayfirst=True)
            df_date = df_date.sort_values('Date')
            
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(x=df_date['Date'], y=df_date['EFF'], mode='lines+markers', name='EFF', line=dict(color='#2E86C1', width=3)))
            fig_trend.add_trace(go.Scatter(x=df_date['Date'], y=df_date['RFT'], mode='lines+markers', name='RFT', line=dict(color='#28B463', width=3)))
            fig_trend.add_hline(y=0.70, line_dash="dash", line_color="red", annotation_text="Cảnh báo EFF < 70%")
            fig_trend.update_layout(yaxis_tickformat='.0%', hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True)

            col_chart1, col_chart2 = st.columns(2)

            with col_chart1:
                st.markdown("### 🏭 Hiệu suất EFF theo Chuyền")
                df_line = df.groupby('Line')[['Target', 'ACT', 'Defect']].sum().reset_index()
                df_line = calculate_metrics(df_line).sort_values('EFF')
                colors = ['#E74C3C' if x < 0.7 else ('#2ECC71' if x > 0.85 else '#F1C40F') for x in df_line['EFF']]
                
                fig_line = px.bar(df_line, x='EFF', y='Line', orientation='h', text='EFF')
                fig_line.update_traces(marker_color=colors, texttemplate='%{text:.1%}', textposition='outside')
                fig_line.update_layout(xaxis_tickformat='.0%', xaxis_range=[0, max(df_line['EFF'] if not df_line.empty else [0]) + 0.2])
                st.plotly_chart(fig_line, use_container_width=True)

            with col_chart2:
                st.markdown("### ⚠️ Top 10 Mã hàng có Lỗi cao nhất")
                df_working = df.groupby('Working')[['Defect', 'ACT']].sum().reset_index()
                df_working = df_working.sort_values('Defect', ascending=False).head(10).sort_values('Defect', ascending=True)
                
                fig_defect = px.bar(df_working, x='Defect', y='Working', orientation='h', text='Defect')
                fig_defect.update_traces(marker_color='#E74C3C', texttemplate='%{text:,.0f}', textposition='outside')
                st.plotly_chart(fig_defect, use_container_width=True)

# ==========================================
# 3. XUẤT BÁO CÁO TUẦN PIVOT
# ==========================================
elif menu == "3. Xuất Báo Cáo Tuần (Pivot Matrix)":
    st.title(f"🧮 Xuất Báo Cáo Tuần Mẫu Pivot (Tuần {report_week})")
    st.markdown("Tính năng này tự động trải ngang dữ liệu theo Ngày (Date) để tạo file **Week Report** chuẩn form.")
    
    uploaded_file = st.file_uploader("Tải lên file dữ liệu thô (PO-Tracking Report)", type=["xlsx", "csv"], key="pivot")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'): raw_df = pd.read_csv(uploaded_file)
            else: raw_df = pd.read_excel(uploaded_file, sheet_name='Report')
                
            raw_df.columns = raw_df.columns.str.strip()
            raw_df.rename(columns={'Sum of Defect': 'Defect', 'Sum Defect': 'Defect'}, inplace=True)
            for col in ['Working', 'Line', 'Date']:
                if col in raw_df.columns:
                    raw_df[col] = raw_df[col].fillna('(Trống)').astype(str).str.strip()
                    raw_df[col] = raw_df[col].replace(r'[\x00-\x1F\x7F-\x9F]', '', regex=True)
                    raw_df[col] = raw_df[col].replace(['nan', ''], '(Trống)')
            raw_df = raw_df[~raw_df['Line'].str.contains('B06|B6', case=False, na=False)]
            for col in ['Target', 'ACT', 'Defect']:
                if col in raw_df.columns:
                    raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

            st.success("Đã phân tích dữ liệu xong. Đang khởi tạo các Bảng Pivot...")
            
            pivot_sheet1 = create_weekly_pivot(raw_df, ['Line'])
            pivot_sheet2 = create_weekly_pivot(raw_df, ['Working'])
            pivot_sheet3 = create_weekly_pivot(raw_df, ['Working', 'Line'])
            
            st.markdown("#### Xem trước Sheet 1 (Theo Line trải ngang theo Ngày)")
            st.dataframe(pivot_sheet1)
            
            output_pivot = io.BytesIO()
            with pd.ExcelWriter(output_pivot, engine='xlsxwriter') as writer:
                pivot_sheet1.to_excel(writer, sheet_name='Sheet 1')
                pivot_sheet2.to_excel(writer, sheet_name='Sheet 2')
                pivot_sheet3.to_excel(writer, sheet_name='Sheet 3')
                
                workbook = writer.book
                pct_fmt = workbook.add_format({'num_format': '0.00%'})
                num_fmt = workbook.add_format({'num_format': '#,##0'})
                
                for sheet_name, df_pivot in zip(['Sheet 1', 'Sheet 2', 'Sheet 3'], [pivot_sheet1, pivot_sheet2, pivot_sheet3]):
                    worksheet = writer.sheets[sheet_name]
                    col_idx = len(df_pivot.index.names)
                    for col_top, col_sub in df_pivot.columns:
                        if col_sub in ['EFF', 'RFT']: worksheet.set_column(col_idx, col_idx, 10, pct_fmt)
                        else: worksheet.set_column(col_idx, col_idx, 10, num_fmt)
                        col_idx += 1
                    worksheet.set_column(0, len(df_pivot.index.names)-1, 15)

            excel_pivot_data = output_pivot.getvalue()
            
            st.download_button(
                label=f"📥 TẢI XUỐNG FILE WEEK REPORT PIVOT (TUẦN {report_week})",
                data=excel_pivot_data,
                file_name=f"Week_Report_Pivot_Week_{report_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        except Exception as e:
            st.error(f"Lỗi: {e}")