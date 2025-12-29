import streamlit as st
import sqlite3
import pandas as pd
import os

# ==========================================
# 0. 系统配置 (Configuration)
# ==========================================
DB_FILE = "tuan_eval.db"
EXCEL_FILE = "members.xlsx"

# 定义4位班干部的学号 (系统会自动识别这些账号拥有“组织评议”权限)
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
                # 强制将学号读取为字符串，防止丢失前导0或变成科学计数法
                df = pd.read_excel(EXCEL_FILE, dtype={'学号': str, '姓名': str})
                count = 0
                for index, row in df.iterrows():
                    name = str(row['姓名']).strip()
                    uid = str(row['学号']).strip()
                    # 默认密码为学号后6位
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
    
    # 获取所有学生 (包括班干部)
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
    # 公式：(得票数 / (总人数-1)) * 100
    total_students = len(students)
    max_peer_votes = total_students - 1 if total_students > 1 else 1
    df['peer_score'] = (df['vote_count'] / max_peer_votes) * 100
    
    # B. 组织评议折算分 (40%)
    # 公式：(获得班干票数 / 4) * 100
    df['org_score'] = (df['officer_vote_count'] / 4) * 100
    
    # C. 综合得分
    # 综合评议得分 = 自评×30% + 团员互评×30% + 组织评议×40%
    df['final_score'] = (df['self_score'] * 0.3) + (df['peer_score'] * 0.3) + (df['org_score'] * 0.4)
    
    # 格式化保留两位小数
    df['final_score'] = df['final_score'].round(2)
    df['peer_score'] = df['peer_score'].round(2)
    df['org_score'] = df['org_score'].round(2)
    
    # 排名 (同分处理：组织分 > 互评票 > 自评)
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
    
    # --- [核心修改] 隐藏 Streamlit 默认菜单和页脚 ---
    hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display:none;}
            </style>
            """
    st.markdown(hide_st_style, unsafe_allow_html=True)
    
    init_db()

    # --- 登录模块 ---
    if 'user' not in st.session_state:
        st.title("🔐 团员评议在线投票系统")
        st.markdown("---")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.info("💡 **提示**：\n\n普通同学请使用 **学号** 登录。\n\n**班干部** 请使用学号登录，系统会自动识别权限。\n\n默认密码为 **学号后 6 位**。")
        
        with col2:
            with st.form("login_form"):
                uid = st.text_input("账号 (学号 / admin)")
                pwd = st.text_input("密码", type="password")
                submitted = st.form_submit_button("登录系统")
                
                if submitted:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT uid, name, role FROM users WHERE uid=? AND password=?", (uid, pwd))
                    user = cur.fetchone()
                    conn.close()
                    
                    if user:
                        # 构造用户数据字典
                        user_data = {'uid': user[0], 'name': user[1], 'role': user[2]}
                        
                        # 如果学号在班干列表里，强制提升为 officer 角色
                        if user_data['uid'] in OFFICER_IDS:
                            user_data['role'] = 'officer'
                            
                        st.session_state['user'] = user_data
                        st.rerun()
                    else:
                        st.error("账号或密码错误。")
        return

    # --- 已登录界面 ---
    user = st.session_state['user']
    
    with st.sidebar:
        st.title("👤 用户信息")
        st.markdown(f"**姓名**: {user['name']}")
        
        if user['role'] == 'officer':
            st.success("身份: 班干部 (组织评议权限)")
        elif user['role'] == 'admin':
            st.error("身份: 管理员")
        else:
            st.info("身份: 团员")
            
        st.markdown("---")
        if st.button("🚪 退出登录", type="primary"):
            del st.session_state['user']
            st.rerun()

    # ==========================
    # 角色界面逻辑
    # ==========================
    
    # 1. 学生和班干部的通用界面
    if user['role'] in ['student', 'officer']:
        st.header(f"👋 你好，{user['name']}")
        
        # 构建标签页
        tabs_list = ["📝 (一) 团员自评", "🗳️ (二) 团员互评 (选10人)"]
        if user['role'] == 'officer':
            tabs_list.append("⚖️ (三) 组织评议 (班干投票)")
            
        tabs = st.tabs(tabs_list)
        
        conn = get_db_connection()
        
        # --- Tab 1: 自评 (30%) ---
        with tabs[0]:
            cur = conn.cursor()
            cur.execute("SELECT score FROM self_evals WHERE uid=?", (user['uid'],))
            exist = cur.fetchone()
            if exist:
                st.success(f"✅ 自评已完成：**{exist[0]} 分**")
            else:
                st.write("请对自己进行打分 (0-100)：")
                with st.form("self_form"):
                    score = st.number_input("分数", 0, 100, step=1)
                    if st.form_submit_button("提交"):
                        cur.execute("INSERT INTO self_evals VALUES (?, ?)", (user['uid'], score))
                        conn.commit()
                        st.rerun()

        # --- Tab 2: 团员互评 (30%) ---
        # 规则：不可选自己，限制最多选10人
        with tabs[1]:
            cur.execute("SELECT count(*) FROM peer_votes WHERE voter_uid=?", (user['uid'],))
            if cur.fetchone()[0] > 0:
                st.success("✅ 团员互评已完成。")
            else:
                st.info("请选择 **10位** 优秀团员 (❌不可选自己)")
                # 排除自己
                candidates = pd.read_sql("SELECT uid, name FROM users WHERE role!='admin' AND uid != ?", conn, params=(user['uid'],))
                options = {row['uid']: f"{row['name']} ({row['uid']})" for i, row in candidates.iterrows()}
                
                # 增加 max_selections=10 限制
                selected = st.multiselect(
                    "候选人列表 (限制最多选10人):", 
                    options.keys(), 
                    format_func=lambda x: options[x], 
                    key="peer_select",
                    max_selections=10
                )
                
                st.caption(f"已选: {len(selected)} / 10")
                if st.button("提交团员互评"):
                    if len(selected) != 10:
                        st.error("规则限制：必须 **凑满 10 人** 才能提交！")
                    else:
                        data = [(user['uid'], tid) for tid in selected]
                        cur.executemany("INSERT INTO peer_votes VALUES (?, ?)", data)
                        conn.commit()
                        st.balloons()
                        st.rerun()

        # --- Tab 3: 组织评议 (40%) ---
        # 规则：仅班干可见，可选自己，限制最多选10人
        if user['role'] == 'officer':
            with tabs[2]:
                st.markdown("### ⚖️ 班干部特别通道")
                
                cur.execute("SELECT count(*) FROM officer_votes WHERE voter_uid=?", (user['uid'],))
                if cur.fetchone()[0] > 0:
                    st.success("✅ 您已完成组织评议投票。")
                else:
                    st.warning("作为班干部，请推选 **10位** 优秀团员 (✅包含可以选自己)")
                    st.markdown("您的投票将直接决定同学们的 **组织评议分 (占40%)**。")
                    
                    # 可选所有人(包括自己)
                    candidates_all = pd.read_sql("SELECT uid, name FROM users WHERE role!='admin'", conn)
                    options_off = {row['uid']: f"{row['name']} ({row['uid']})" for i, row in candidates_all.iterrows()}
                    
                    # 增加 max_selections=10 限制
                    selected_off = st.multiselect(
                        "请慎重推选 10 人 (限制最多选10人):", 
                        options_off.keys(), 
                        format_func=lambda x: options_off[x], 
                        key="officer_select",
                        max_selections=10
                    )
                    
                    st.caption(f"已选: {len(selected_off)} / 10")
                    if st.button("提交组织评议"):
                        if len(selected_off) != 10:
                            st.error("规则限制：必须 **凑满 10 人** 才能提交！")
                        else:
                            data = [(user['uid'], tid) for tid in selected_off]
                            cur.executemany("INSERT INTO officer_votes VALUES (?, ?)", data)
                            conn.commit()
                            st.balloons()
                            st.success("组织评议提交成功！")
                            st.rerun()
                            
        conn.close()

    # 2. 管理员界面
    elif user['role'] == 'admin':
        st.header("📊 评议结果控制台")
        
        # 实时统计数据
        conn = get_db_connection()
        student_count = pd.read_sql("SELECT count(*) FROM users WHERE role!='admin'", conn).iloc[0,0]
        self_done = pd.read_sql("SELECT count(*) FROM self_evals", conn).iloc[0,0]
        peer_done = pd.read_sql("SELECT count(DISTINCT voter_uid) FROM peer_votes", conn).iloc[0,0]
        off_done = pd.read_sql("SELECT count(DISTINCT voter_uid) FROM officer_votes", conn).iloc[0,0]
        conn.close()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总团员数", student_count)
        c2.metric("已自评", self_done)
        c3.metric("已互评", peer_done)
        c4.metric("班干已投", f"{off_done}/4")
        
        st.markdown("---")
        
        if st.button("🔄 刷新 / 计算最终结果"):
            df = calculate_results()
            
            st.subheader("🏆 最终排名 (Top 10)")
            st.table(df[df['rank']<=10][['rank', 'name', 'final_score', 'result']])
            
            st.subheader("📑 详细数据表")
            st.dataframe(df)
            
            st.download_button("📥 下载完整结果 CSV", df.to_csv().encode('utf-8-sig'), "result.csv")
        
        with st.expander("⚠️ 危险操作区"):
            st.warning("如果测试完毕需要正式使用，请点击下方按钮清空数据库。")
            if st.button("🗑️ 清空所有投票数据"):
                conn = get_db_connection()
                conn.execute("DELETE FROM self_evals")
                conn.execute("DELETE FROM peer_votes")
                conn.execute("DELETE FROM officer_votes")
                conn.commit()
                st.success("数据已清空，可以开始正式投票。")
                st.rerun()

if __name__ == "__main__":
    main()
