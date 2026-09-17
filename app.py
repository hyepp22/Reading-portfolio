import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# -------------------------------------------------------------------
# 1. 데이터베이스 초기화
# -------------------------------------------------------------------
DB_FILE = "reading_portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 독서 기록 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS reading_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            student_name TEXT,
            pin TEXT,
            book_title TEXT,
            author TEXT,
            log_date TEXT,
            pages_read TEXT,
            summary TEXT,
            quote TEXT,
            qa_pair TEXT,
            reflection TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 교사 수행평가 채점 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            student_name TEXT,
            book_title TEXT,
            understanding_score INT,  -- 내용 이해도
            completeness_score INT,   -- 작성 충실도
            depth_score INT,          -- 감상의 깊이
            frequency_score INT,      -- 작성 횟수
            total_score INT,          -- 총점
            feedback TEXT,            -- 교사 피드백
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, book_title) ON CONFLICT REPLACE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------
# 2. Page 설정 및 대시보드 구조
# -------------------------------------------------------------------
st.set_page_config(page_title="중학생 독서 포트폴리오 시스템", page_icon="📚", layout="wide")

st.title("📚 중학교 독서 포트폴리오 & 수행평가 시스템")
st.caption("15~17차시 한 학기 독서 활동을 기록하고 교사 피드백 및 채점을 진행하는 공간입니다.")

# 사이드바 로그인 / 모드 선택
st.sidebar.header("🔐 로그인 / 모드 선택")
user_type = st.sidebar.radio("사용자 유형을 선택하세요", ["학생용 (기록 및 조회)", "교사용 (관리 및 채점)"])

# -------------------------------------------------------------------
# 3. 학생용 화면 (기록 작성 및 본인 포트폴리오 확인)
# -------------------------------------------------------------------
if user_type == "학생용 (기록 및 조회)":
    st.subheader("👨‍🎓 학생 로그인 및 독서 기록 작성")
    
    col_login1, col_login2, col_login3 = st.columns(3)
    with col_login1:
        student_id = st.text_input("학번 (예: 10301)", key="st_id")
    with col_login2:
        student_name = st.text_input("이름", key="st_name")
    with col_login3:
        pin = st.text_input("고유번호 (비밀번호 4자리)", type="password", key="st_pin")

    if student_id and student_name and pin:
        st.success(f"[{student_id} {student_name}] 학생 환영합니다!")
        
        tab1, tab2 = st.tabs(["📝 오늘의 독서 기록 작성하기", "📖 나의 독서 포트폴리오 모아보기"])
        
        # Tab 1: 독서 기록 작성
        with tab1:
            st.markdown("#### 오늘 읽은 차시의 독서 기록을 정성껏 작성해 주세요.")
            
            with st.form("reading_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    book_title = st.text_input("책 제목 *")
                    author = st.text_input("작가 이름 *")
                with col2:
                    log_date = st.date_input("읽은 날짜", datetime.now()).strftime("%Y-%m-%d")
                    pages_read = st.text_input("읽은 페이지 (예: 15p ~ 42p) *")
                
                summary = st.text_area("1. 오늘 읽은 부분 짧은 요약 (주요 줄거리/내용)", height=100)
                quote = st.text_area("2. 가장 인상 깊은 문장 (구절과 이유)", height=80)
                qa_pair = st.text_area("3. 읽은 부분에 대한 질문과 나의 답변 (스스로 묻고 답하기)", height=100)
                reflection = st.text_area("4. 나의 생각과 느낌 (느낀 점, 깨달은 점, 삶과의 연결)", height=120)
                
                submitted = st.form_submit_button("독서 기록 제출하기")
                
                if submitted:
                    if not book_title or not author or not pages_read or not summary or not reflection:
                        st.error("필수 항목(*) 및 작성 내용을 빠짐없이 입력해 주세요!")
                    else:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO reading_logs 
                            (student_id, student_name, pin, book_title, author, log_date, pages_read, summary, quote, qa_pair, reflection)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (student_id, student_name, pin, book_title, author, log_date, pages_read, summary, quote, qa_pair, reflection))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.success("독서 기록이 성공적으로 저장되었습니다!")

        # Tab 2: 본인 기록 보기
        with tab2:
            st.markdown("#### 내가 누적 기록한 독서 포트폴리오")
            conn = sqlite3.connect(DB_FILE)
            query = "SELECT log_date, book_title, author, pages_read, summary, quote, qa_pair, reflection FROM reading_logs WHERE student_id = ? AND pin = ? ORDER BY id DESC"
            df_my_logs = pd.read_sql_query(query, conn, params=(student_id, pin))
            conn.close()
            
            if df_my_logs.empty:
                st.info("아직 제출한 독서 기록이 없거나 학번/고유번호가 일치하지 않습니다.")
            else:
                st.metric(label="총 작성 횟수", value=f"{len(df_my_logs)}회 / (목표 15~17차시)")
                for idx, row in df_my_logs.iterrows():
                    with st.expander(f"📌 [{row['log_date']}] {row['book_title']} ({row['pages_read']})"):
                        st.write(f"**작가:** {row['author']}")
                        st.write(f"**1. 짧은 요약:** {row['summary']}")
                        st.write(f"**2. 인상 깊은 문장:** {row['quote']}")
                        st.write(f"**3. 질문과 답변:** {row['qa_pair']}")
                        st.write(f"**4. 생각과 느낌:** {row['reflection']}")

# -------------------------------------------------------------------
# 4. 교사용 화면 (진도 모니터링, 포트폴리오 확인, 수행평가 채점)
# -------------------------------------------------------------------
else:
    st.subheader("👩‍🏫 교사 관리 및 수행평가 채점 모드")
    teacher_pw = st.sidebar.text_input("교사 비밀번호 입력", type="password")
    
    # 교사 비밀번호 검증 (비밀번호: 0923)
    if teacher_pw != "0923":
        st.warning("교사전용 비밀번호를 입력해야 접근할 수 있습니다.")
    else:
        st.success("교사 인증이 완료되었습니다.")
        
        conn = sqlite3.connect(DB_FILE)
        df_all_logs = pd.read_sql_query("SELECT * FROM reading_logs ORDER BY student_id ASC, id ASC", conn)
        conn.close()
        
        t_tab1, t_tab2, t_tab3 = st.tabs(["📊 학생별 진도 현황", "🔍 포트폴리오 개별 검토 및 채점", "📥 수행평가 결과 집계"])
        
        # (이하 기존 교사용 화면 동일...)
        
        # Tab 1: 진도 현황
        with t_tab1:
            st.markdown("#### 학생별 작성 횟수 및 진도 요약")
            if df_all_logs.empty:
                st.info("등록된 독서 기록이 없습니다.")
            else:
                summary_df = df_all_logs.groupby(['student_id', 'student_name', 'book_title']).agg(
                    작성횟수=('id', 'count'),
                    최근작성일=('log_date', 'max')
                ).reset_index()
                
                # 작성 횟수 기준 미달(예: 15차시 미만) 시각적 표시
                st.dataframe(summary_df, use_container_width=True)

        # Tab 2: 개별 검토 및 채점
        with t_tab2:
            if df_all_logs.empty:
                st.info("등록된 독서 기록이 없습니다.")
            else:
                students = df_all_logs['student_id'].unique()
                selected_student_id = st.selectbox("학생 선택", students, format_func=lambda x: f"{x} - {df_all_logs[df_all_logs['student_id']==x]['student_name'].iloc[0]}")
                
                student_logs = df_all_logs[df_all_logs['student_id'] == selected_student_id]
                student_name = student_logs['student_name'].iloc[0]
                books = student_logs['book_title'].unique()
                selected_book = st.selectbox("대상 책 선택", books)
                
                filtered_logs = student_logs[student_logs['book_title'] == selected_book]
                
                st.write("---")
                col_left, col_right = st.columns([3, 2])
                
                # 좌측: 학생 누적 포트폴리오
                with col_left:
                    st.markdown(f"### 📖 {student_name} 학생의 [{selected_book}] 포트폴리오 (총 {len(filtered_logs)}회 작성)")
                    for idx, row in filtered_logs.iterrows():
                        with st.expander(f"차시 기록: {row['log_date']} ({row['pages_read']})"):
                            st.write(f"**요약:** {row['summary']}")
                            st.write(f"**인상 깊은 문장:** {row['quote']}")
                            st.write(f"**질문과 답변:** {row['qa_pair']}")
                            st.write(f"**생각과 느낌:** {row['reflection']}")
                
                # 우측: 수행평가 채점 폼
                with col_right:
                    st.markdown("### 📝 수행평가 채점 및 피드백")
                    
                    # 기존 채점 내역이 있는지 조회
                    conn = sqlite3.connect(DB_FILE)
                    eval_df = pd.read_sql_query("SELECT * FROM evaluations WHERE student_id = ? AND book_title = ?", 
                                                conn, params=(selected_student_id, selected_book))
                    conn.close()
                    
                    default_u = int(eval_df['understanding_score'].iloc[0]) if not eval_df.empty else 25
                    default_c = int(eval_df['completeness_score'].iloc[0]) if not eval_df.empty else 25
                    default_d = int(eval_df['depth_score'].iloc[0]) if not eval_df.empty else 25
                    default_f = int(eval_df['frequency_score'].iloc[0]) if not eval_df.empty else 25
                    default_fb = eval_df['feedback'].iloc[0] if not eval_df.empty else ""

                    with st.form("eval_form"):
                        score_u = st.slider("1. 내용 이해도 (25점 만점)", 0, 25, default_u)
                        score_c = st.slider("2. 작성 충실도 (25점 만점)", 0, 25, default_c)
                        score_d = st.slider("3. 감상의 깊이 (25점 만점)", 0, 25, default_d)
                        score_f = st.slider("4. 작성 횟수 및 누락 여부 (25점 만점)", 0, 25, default_f)
                        
                        total = score_u + score_c + score_d + score_f
                        st.markdown(f"#### 💯 평가 총점: **{total} / 100점**")
                        
                        teacher_feedback = st.text_area("교사 한줄 피드백 및 조언", value=default_fb)
                        
                        save_eval = st.form_submit_button("채점 결과 저장하기")
                        if save_eval:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO evaluations 
                                (student_id, student_name, book_title, understanding_score, completeness_score, depth_score, frequency_score, total_score, feedback)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (selected_student_id, student_name, selected_book, score_u, score_c, score_d, score_f, total, teacher_feedback))
                            conn.commit()
                            conn.close()
                            st.success("채점 및 피드백 저장 완료!")

        # Tab 3: 전체 결과 다운로드
        with t_tab3:
            st.markdown("#### 전체 학생 수행평가 성적표 내보내기")
            conn = sqlite3.connect(DB_FILE)
            df_eval_all = pd.read_sql_query("SELECT * FROM evaluations ORDER BY student_id ASC", conn)
            conn.close()
            
            if df_eval_all.empty:
                st.info("아직 채점된 내역이 없습니다.")
            else:
                st.dataframe(df_eval_all, use_container_width=True)
                csv = df_eval_all.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 수행평가 성적표 (CSV/Excel용) 다운로드",
                    data=csv,
                    file_name="reading_evaluation_results.csv",
                    mime="text/csv"
                )
