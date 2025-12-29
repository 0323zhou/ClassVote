import streamlit as st
import sqlite3
import pandas as pd
import os

# ==========================================
# 0. 系统配置 (Configuration)
# ==========================================
DB_FILE = "tuan_eval.db"
EXCEL_FILE = "members.xlsx"

# 在此定义4位班干部的学号
OFFICER_IDS = [
    "251812037", # 余维乐
    "251812057", # 刘荣旭
    "251812069", # 周文丽
    "251812070"  # 黄媛媛
]

# ==========================================
# 1. 数据库配置与初始化 (Model Layer)
# ==========================================

def init_db():
    """初始化数据库表结构，并从Excel导入真实用户数据"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    name TEXT,
                    role TEXT,
                    password TEXT)''')
    
    # 1. 自评表
    c.execute('''CREATE TABLE IF NOT EXISTS self_evals (
                    uid TEXT PRIMARY KEY,
                    score REAL)''')
    
    # 2. 团员互评表 (30%)
    c.execute('''CREATE TABLE IF NOT EXISTS peer_votes (
                    voter_uid TEXT,
                    candidate_uid TEXT,
                    PRIMARY KEY (voter_uid, candidate_uid))''')
    
    # 3. 组织评议表 (40%) - 记录班干部的投票
    c.execute('''CREATE TABLE IF NOT EXISTS officer_votes (
                    voter_uid TEXT,
                    candidate_uid TEXT,
                    PRIMARY KEY (voter_uid, candidate_uid))''')
    
    # --- 数据初始化逻辑 ---
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        print("检测到首次运行，正在初始化数据...")
        
        # 创建管理员
        c.execute("INSERT INTO users VALUES ('admin', '管理员', 'admin', '123456')")
        
        # 从 Excel 导入学生名单
        if os.path.exists(EXCEL_FILE):
            try:
                df = pd.read_excel(EXCEL_FILE, dtype={'学号': str, '姓名': str})
                count = 0
                for index, row in df.iterrows():
                    name = str(row['姓名']).strip()
                    uid = str(row['学号']).strip()
                    password = uid[-6:] if len(uid) >= 6 else uid
                    
                    c.execute("INSERT INTO users VALUES (?, ?, 'student', ?)", (uid, name, password))
                    count += 1
                
                print(f"✅ 成功导入 {count} 位同学数据！")
                
            except Exception as e:
                print(f"❌ 读取 {EXCEL_FILE} 失败: {e}")
        else:
            print(f"⚠️ 未找到 {EXCEL_FILE} 文件！")

        conn.commit()
    
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# ==========================================
# 2. 核心算法逻辑 (Controller Layer)
# ==========================================

def calculate_results():
    """
    计算最终得分与排名
    """
    conn = get_db_connection()
    
    # 获取所有学生
    students = pd.read_sql("SELECT uid, name FROM users WHERE role='student' OR role='officer'", conn)
    
    # 1. 获取自评分
    self_df = pd.read_sql("SELECT uid, score as self_score FROM self_evals", conn)
    
    # 2. 统计团员互评 (票数)
    votes_df = pd.read_sql("SELECT candidate_uid as uid, COUNT(*) as vote_count FROM peer_votes GROUP BY candidate_uid", conn)
    
    # 3. 统计组织评议 (班干票数)
    officer_votes_df = pd.read_sql("SELECT candidate_uid as uid, COUNT(*) as officer_vote_count FROM officer_votes GROUP BY candidate_uid", conn)
    
    # 合并数据
    df = students.merge(self_df, on='uid', how='left').fillna(0)
    df = df.merge(votes_df, on='uid', how='left').fillna(0)
    df = df.merge(officer_votes_df, on='uid', how='left').fillna(0)
    
    # --- 分数计算逻辑 ---
    
    # A. 团员互评折算分 (30%)
    total_students = len(students)
    max_peer_votes = total_students - 1 if total_students > 1 else 1
    df['peer_score'] = (df['vote_count'] / max_peer_votes) * 100
    
    # B. 组织评议折算分 (40%)
    df['org_score'] = (df['officer_vote_count'] / 4) * 100
    
    # C. 综合得分
    # 综合评议得分 = 自评×30% + 团员互评×30% + 组织评议×40%
    df['final_score'] = (df['self_score'] * 0.3) + (df['peer_score'] * 0.3) + (df['org_score'] * 0.4)
    
    # 格式化
    df['final_score'] = df['final_score'].round(2)
    df['peer_score'] = df['peer_score'].round(2)
    df['org_score'] = df['org_score'].round(2)
    
    # 排名
    df = df.sort_values(by=['final_score', 'org_score', 'vote_count', 'self_score'], ascending=[False, False, False, False])
    
    # 评定结果
    df['rank'] = range(1, len(df) + 1)
    df['result'] = df['rank'].apply(lambda x: "优秀团员" if x <= 10 else "合格团员")
    
    conn.close()
    return df

# ==========================================
# 3. 前端界面 (View Layer)
# ==========================================

def main():
    st.set_page_config(page_title="团员评议系统", layout="wide")
    
    # >>>>>>>>>>>>>>> 在这里插入隐藏代码 (开始) >>>>>>>>>>>>>>>
    hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display:none;}
            </style>
            """
    st.markdown(hide_st_style, unsafe_allow_html=True)
    # <<<<<<<<<<<<<<< 在这里插入隐藏代码 (结束) <<<<<<<<<<<<<<<

    init_db()

    # --- 登录模块 ---
    if 'user' not in st.session_state:
        st.title("🔐 团员评议在线投票系统")
        st.markdown("---")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.info("💡 **提示**：\n\n普通同学请使用 **学号** 登录。\n\n**班干部** 请使用学号登录，系统会自动识别权限。")
        
        with col2:
            with st.form("login_form"):
                uid = st.text_input("账号 (学号 / admin)")
                pwd = st.text_input("密码 (默认学号后6位)", type="password")

