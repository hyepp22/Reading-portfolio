import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import openai  # AI 자동 채점용 (pip install openai)

DB_FILE = "reading_portfolio.db"

# -------------------------------------------------------------------
# 1. DB 초기화
# -------------------------------------------------------------------
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
    # 평가 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            student_name TEXT,
            book_title TEXT,
            score_selection INT,
            score_attitude INT,
            score_summary INT,
            score_reflection INT,
            score_question INT,
            score_writing INT,
            score_completeness INT,
            cat1_total INT,
            cat2_total INT,
            cat3_total INT,
            total_score INT,
            feedback TEXT,
            is_auto_graded INTEGER DEFAULT 0,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, book_title) ON CONFLICT REPLACE
        )
    ''')
    # 수업 진행 날짜 관리 테이블 (교사가 허용한 날짜)
    c.execute('''
        CREATE TABLE IF NOT EXISTS allowed_dates (
            allowed_date TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------
# 2. UI & 태블릿 최적화 CSS 적용
# -------------------------------------------------------------------
st.set_page_config(page_title="중학생 독서 포트폴리오", page_icon="📚", layout="wide")

# 태블릿 환경을 위한 터치 친화적 CSS
st.markdown("""
    <style>
    /* 입력창 및 버튼 크기 확대 (태블릿 터치 용이) */
    .stTextInput input, .stTextArea textarea, .stSelectbox, .stButton button {
        font-size: 18px !important;
        padding: 12px !important;
        border-radius: 10px !important;
    }
    .stButton button {
        height: 55px !important;
        background-color: #4CAF50 !important;
        color: white !important;
        font-weight: bold !important;
    }
    /* 카드형 컨테이너 스타일 */
    .card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 3. 사용자 구분 및 접속
# -------------------------------------------------------------------
st.sidebar.header("🔐 접속 모드")
user_type = st.sidebar.radio("모드를 선택하세요", ["👨‍🎓 학생용 (독서 기록)", "👩‍🏫 교사용 (관리 및 자동채점)"])

# -------------------------------------------------------------------
# 4. 학생용 화면 (태블릿 UI + 특정 날짜만 작성 가능 로직)
# -------------------------------------------------------------------
if user_type == "👨‍🎓 학생용 (독서 기록)":
    st.title("📚 나의 독서 포트폴리오 (학생용)")
    
    # 1단계: 간단 학생 로그인
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        student_id = st.text_input("학번 (예: 10301)", key="s_id")
    with c2:
        student_name = st.text_input("이름", key="s_name")
    with c3:
        pin = st.text_input("고유번호 4자리", type="password", key="s_pin")
    st.markdown("</div>", unsafe_allow_html=True)

    if student_id and student_name and pin:
        today_str = date.today().strftime("%Y-%m-%d")
        
        # 오늘 날짜가 교사가 허용한 수업 날짜인지 DB 확인
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT allowed_date FROM allowed_dates WHERE allowed_date = ?", (today_str,))
        is_allowed = c.fetchone()
        conn.close()

        tab1, tab2 = st.tabs(["📝 오늘의 독서 기록 쓰기", "📖 내 기록 모아보기"])

        with tab1:
            if not is_allowed:
                st.error(f"⛔ 오늘은 독서 기록 작성 날짜가 아닙니다. (오늘 날짜: {today_str})")
                st.info("💡 선생님이 수업 시간에 독서 기록 작성을 열어주신 날에만 입력이 가능합니다.")
            else:
                st.success(f"✅ 오늘은 독서 기록 작성일입니다! 차분하게 작성을 진행해 주세요.")
                
                with st.form("tablet_reading_form"):
                    st.markdown("### 📖 기본 정보")
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        book_title = st.text_input("책 제목 *")
                        author = st.text_input("작가 이름 *")
                    with col_b2:
                        pages_read = st.text_input("오늘 읽은 페이지 (예: 12~35p) *")
                    
                    st.markdown("---")
                    st.markdown("### ✏️ 독서 활동 내용")
                    summary = st.text_area("1. 오늘 읽은 내용 짧은 요약 (핵심 줄거리)", height=120)
                    quote = st.text_area("2. 가장 인상 깊은 문장과 이유", height=100)
                    qa_pair = st.text_area("3. 읽은 내용에 대한 질문과 나의 답변", height=120)
                    reflection = st.text_area("4. 나의 생각과 느낌 (느낀점/깨달은점)", height=140)

                    submit_btn = st.form_submit_button("🚀 독서 기록 제출하기 (터치)")

                    if submit_btn:
                        if not book_title or not pages_read or not summary or not reflection:
                            st.error("필수 내용들을 빠짐없이 입력해 주세요!")
                        else:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO reading_logs 
                                (student_id, student_name, pin, book_title, author, log_date, pages_read, summary, quote, qa_pair, reflection)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (student_id, student_name, pin, book_title, author, today_str, pages_read, summary, quote, qa_pair, reflection))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.success("오늘의 독서 기록이 제출되었습니다!")

        with tab2:
            st.markdown("#### 내 누적 포트폴리오")
            conn = sqlite3.connect(DB_FILE)
            df_my = pd.read_sql_query("SELECT * FROM reading_logs WHERE student_id = ? AND pin = ? ORDER BY id DESC", conn, params=(student_id, pin))
            conn.close()
            
            if df_my.empty:
                st.info("아직 제출된 기록이 없습니다.")
            else:
                for idx, row in df_my.iterrows():
                    with st.expander(f"📌 [{row['log_date']}] {row['book_title']} ({row['pages_read']})"):
                        st.write(f"**요약:** {row['summary']}")
                        st.write(f"**인상 깊은 문장:** {row['quote']}")
                        st.write(f"**질문/답변:** {row['qa_pair']}")
                        st.write(f"**느낀점:** {row['reflection']}")

# -------------------------------------------------------------------
# 5. 교사용 화면 (날짜 제한 설정 + AI 자동 채점)
# -------------------------------------------------------------------
else:
    st.title("👩‍🏫 교사 관리 및 AI 자동 채점 시스템")
    teacher_pw = st.sidebar.text_input("교사 비밀번호", type="password")
    
    if teacher_pw != "0923":
        st.warning("교사전용 비밀번호를 입력해야 접근할 수 있습니다.")
    else:
        st.success("교사 인증이 완료되었습니다.")
        
        t_tab1, t_tab2, t_tab3 = st.tabs(["📅 작성 가능 날짜 관리", "🤖 AI 자동 채점 & 검토", "📥 성적 집계 다운로드"])
        
        # Tab 1: 제출 허용 날짜 지정
        with t_tab1:
            st.markdown("### 📅 독서 기록 작성 가능 날짜 설정")
            st.caption("선택한 날짜에만 학생들이 독서 포트폴리오를 제출할 수 있습니다.")
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                new_date = st.date_input("수업/작성 허용 날짜 추가", date.today()).strftime("%Y-%m-%d")
                if st.button("날짜 허용 목록에 추가"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT OR IGNORE INTO allowed_dates VALUES (?)", (new_date,))
                    conn.commit()
                    conn.close()
                    st.success(f"[{new_date}]가 작성 허용 날짜로 등록되었습니다.")
            
            with col_d2:
                conn = sqlite3.connect(DB_FILE)
                allowed_df = pd.read_sql_query("SELECT allowed_date AS '허용된 날짜 목록' FROM allowed_dates ORDER BY allowed_date DESC", conn)
                conn.close()
                st.dataframe(allowed_df, use_container_width=True)

        # Tab 2: LLM 기반 자동 채점
        with t_tab2:
            st.markdown("### 🤖 GPT AI 기반 루브릭 자동 채점")
            api_key = st.text_input("OpenAI API Key 입력 (자동채점용)", type="password")
            
            conn = sqlite3.connect(DB_FILE)
            df_all = pd.read_sql_query("SELECT * FROM reading_logs ORDER BY student_id ASC", conn)
            conn.close()
            
            if df_all.empty:
                st.info("제출된 독서 기록이 없습니다.")
            else:
                students = df_all['student_id'].unique()
                sel_student = st.selectbox("학생 선택", students, format_func=lambda x: f"{x} - {df_all[df_all['student_id']==x]['student_name'].iloc[0]}")
                
                s_logs = df_all[df_all['student_id'] == sel_student]
                s_name = s_logs['student_name'].iloc[0]
                sel_book = st.selectbox("책 선택", s_logs['book_title'].unique())
                
                target_logs = s_logs[s_logs['book_title'] == sel_book]
                
                # 전체 누적 내용 텍스트로 합성
                combined_text = ""
                for _, r in target_logs.iterrows():
                    combined_text += f"\n[날짜: {r['log_date']}]\n- 요약: {r['summary']}\n- 문장: {r['quote']}\n- 질문답변: {r['qa_pair']}\n- 느낌: {r['reflection']}\n"
                
                col_ui1, col_ui2 = st.columns(2)
                with col_ui1:
                    st.markdown(f"#### 📖 {s_name} 학생 누적 기록 (총 {len(target_logs)}회)")
                    st.text_area("전체 작성 내용", combined_text, height=400)
                
                with col_ui2:
                    st.markdown("#### 🤖 AI 채점 실행하기")
                    if st.button("✨ 루브릭 기준 AI 자동 채점 실행"):
                        if not api_key:
                            st.error("OpenAI API 키를 먼저 입력해 주세요!")
                        else:
                            with st.spinner("AI가 학생의 글을 분석하여 루브릭 기준으로 평가 중입니다..."):
                                prompt = f"""
                                당신은 중학교 국어 교사입니다. 아래 학생의 독서 포트폴리오 작성을 보고 평가기준표(루브릭)에 맞춰 채점해주세요.

                                [채점 기준표]
                                1. 핵심 내용 요약 (10, 5, 0점)
                                2. 감상 및 의견 (10, 5, 0점)
                                3. 질문 작성 수준 (10, 5, 0점)
                                4. 문장력 및 논리성 (20, 15, 10, 0점)
                                5. 작성 충실도 (20, 15, 10, 0점)

                                [학생 작성 내용]
                                {combined_text}

                                [응답 형식]
                                반드시 아래 형식을 정확히 지켜 답하세요:
                                요약점수: [점수]
                                감상점수: [점수]
                                질문점수: [점수]
                                문장력점수: [점수]
                                충실도점수: [점수]
                                피드백: [학생을 위한 2줄 총평]
                                """
                                client = openai.OpenAI(api_key=api_key)
                                response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": prompt}]
                                )
                                res_text = response.choices[0].message.content
                                st.success("AI 채점 완료!")
                                st.text(res_text)

        # Tab 3: 결과 집계
        with t_tab3:
            st.markdown("#### 전체 성적표 내보내기")
            conn = sqlite3.connect(DB_FILE)
            df_eval_all = pd.read_sql_query("SELECT * FROM evaluations", conn)
            conn.close()
            st.dataframe(df_eval_all, use_container_width=True)
