import streamlit as st
import pandas as pd
import numpy as np
import pymongo
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Dashboard Tổng Quan PO", layout="wide", page_icon="📈")

# --- CẤU HÌNH MONGODB ---
MONGO_URI = "mongodb://admin:123456@192.168.40.168:27017/"
DB_NAME = "po_tracking_db"
COLLECTION_NAME = "daily_reports"

@st.cache_resource(ttl=60) # Cập nhật lại connection mỗi 60s để đảm bảo lấy data mới
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

st.markdown("<h3 style='text-align: center; color: #1E88E5;'>CÔNG TY TNHH LONG VĨ VIỆT NAM - LONGWAY VIETNAM CO., LTD</h3>", unsafe_allow_html=True)
st.title("📈 Dashboard Hiệu Suất Tổng Quan (EFF & RFT)")

if client is None:
    st.error("🔴 Không thể kết nối Database để tải Dashboard. Vui lòng kiểm tra Server MongoDB.")
else:
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Kéo thẳng data từ MongoDB
    data_from_db = list(collection.find({}, {'_id': 0}))
    
    if len(data_from_db) == 0:
        st.warning("Hệ thống chưa có dữ liệu. Vui lòng sử dụng Tool Xử lý để tải file lên trước.")
    else:
        df = pd.DataFrame(data_from_db)
        
        # Đảm bảo có cột 'Week' cho cả data cũ và mới
        if 'Week' not in df.columns:
            date_calc = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
            df['Week'] = date_calc.dt.isocalendar().week.astype(float).fillna(-1).astype(int)
        
        # Lọc Tuần
        available_weeks = sorted([int(w) for w in df['Week'].unique() if w != -1])
        if available_weeks:
            st.markdown("### 🗓️ Lọc Dữ Liệu Theo Tuần")
            col_w1, col_w2 = st.columns([1, 4])
            with col_w1:
                selected_week = st.selectbox("Chọn Tuần", available_weeks, index=len(available_weeks)-1)
            with col_w2:
                # Add a vertical spacing
                st.write("")
                st.write("")
                st.info(f"Đang hiển thị báo cáo của **Tuần {selected_week}**. Nếu có Tuần mới, hãy chọn lại để so sánh.")
            
            # Áp dụng bộ lọc
            df = df[df['Week'] == selected_week].copy()

        df = calculate_metrics(df)
        
        # --- TÍNH TOÁN KPI TỔNG ---
        total_target = df['Target'].sum()
        total_act = df['ACT'].sum()
        total_defect = df['Defect'].sum()
        avg_eff = total_act / total_target if total_target > 0 else 0
        avg_rft = 1 - (total_defect / total_act) if total_act > 0 else 0

        # --- HIỂN THỊ KPI ---
        st.markdown("### 🎯 Chỉ Số Trọng Yếu")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🎯 Tổng Target", f"{total_target:,.0f}")
        col2.metric("✅ Tổng ACT", f"{total_act:,.0f}")
        col3.metric("⚡ Hiệu Suất (EFF)", f"{avg_eff * 100:.2f}%", delta="Đạt Mức Đỏ" if avg_eff < 0.70 else "Tốt")
        col4.metric("🛠️ Lỗi (RFT)", f"{avg_rft * 100:.2f}%", delta="Nguy Hiểm" if avg_rft < 0.99 else "An Toàn", delta_color="inverse")

        st.divider()

        # --- BIỂU ĐỒ 1: XU HƯỚNG THEO THỜI GIAN ---
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

        # --- BIỂU ĐỒ 2: EFF THEO CHUYỀN ---
        with col_chart1:
            st.markdown("### 🏭 Hiệu suất EFF theo Chuyền")
            df_line = df.groupby('Line')[['Target', 'ACT', 'Defect']].sum().reset_index()
            df_line = calculate_metrics(df_line).sort_values('EFF')
            colors = ['#E74C3C' if x < 0.7 else ('#2ECC71' if x > 0.85 else '#F1C40F') for x in df_line['EFF']]
            
            fig_line = px.bar(df_line, x='EFF', y='Line', orientation='h', text='EFF')
            fig_line.update_traces(marker_color=colors, texttemplate='%{text:.1%}', textposition='outside')
            fig_line.update_layout(xaxis_tickformat='.0%', xaxis_range=[0, max(df_line['EFF'] if not df_line.empty else [0]) + 0.2])
            st.plotly_chart(fig_line, use_container_width=True)

        # --- BIỂU ĐỒ 3: TOP DEFECT ---
        with col_chart2:
            st.markdown("### ⚠️ Top 10 Mã hàng có Lỗi cao nhất")
            df_working = df.groupby('Working')[['Defect', 'ACT']].sum().reset_index()
            df_working = df_working.sort_values('Defect', ascending=False).head(10).sort_values('Defect', ascending=True)
            
            fig_defect = px.bar(df_working, x='Defect', y='Working', orientation='h', text='Defect')
            fig_defect.update_traces(marker_color='#E74C3C', texttemplate='%{text:,.0f}', textposition='outside')
            st.plotly_chart(fig_defect, use_container_width=True)

        # --- BẢNG SỐ LIỆU CHI TIẾT ---
        st.divider()
        st.markdown("### 📊 Chi Tiết Số Liệu Báo Cáo")
        
        if not df.empty:
            global_totals = get_global_totals(df)

            # Bảng 1
            df1 = df.groupby('Line', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df1 = calculate_metrics(df1)
            df1 = add_grand_total(df1, 'Line', global_totals)
            
            # Bảng 2
            df2 = df.groupby('Date', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df2 = calculate_metrics(df2)
            df2['Sort_Date'] = pd.to_datetime(df2['Date'], errors='coerce', dayfirst=True)
            df2 = df2.sort_values(by='Sort_Date', na_position='first').drop(columns=['Sort_Date']).reset_index(drop=True)
            df2 = add_grand_total(df2, 'Date', global_totals)
            
            # Bảng 3
            df3 = df.groupby('Working', dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df3 = calculate_metrics(df3)
            df3 = df3.sort_values(by='EFF', ascending=True).reset_index(drop=True)
            df3 = add_grand_total(df3, 'Working', global_totals) 
            
            # Bảng 4
            df4 = df.groupby(['Working', 'Line'], dropna=False)[['Target', 'ACT', 'Defect']].sum().reset_index()
            df4 = calculate_metrics(df4)
            df4 = df4.sort_values(by='EFF', ascending=True).reset_index(drop=True)

            format_dict = {'Target': '{:,.0f}', 'ACT': '{:,.0f}', 'Defect': '{:,.0f}', 'EFF': '{:.2%}', 'RFT': '{:.2%}'}
            
            styled_df1 = df1.style.apply(lambda d: style_dataframe(d, 1), axis=None).format(format_dict)
            styled_df2 = df2.style.apply(lambda d: style_dataframe(d, 2), axis=None).format(format_dict)
            styled_df3 = df3.style.apply(lambda d: style_dataframe(d, 3), axis=None).format(format_dict)
            styled_df4 = df4.style.apply(lambda d: style_dataframe(d, 4), axis=None).format(format_dict)

            tab1, tab2, tab3, tab4 = st.tabs(["Hiệu suất theo Line", "Hiệu suất theo Ngày", "Hiệu suất theo Mã hàng", "Chi tiết Working & Line"])
            
            with tab1:
                st.dataframe(styled_df1, use_container_width=True)
            with tab2:
                st.dataframe(styled_df2, use_container_width=True)
            with tab3:
                st.dataframe(styled_df3, use_container_width=True)
            with tab4:
                st.dataframe(styled_df4, use_container_width=True)
        else:
            st.warning("Không có dữ liệu chi tiết cho tuần này.")