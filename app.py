import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import openai

DB_FILE = "reading_portfolio.db"

# -------------------------------------------------------------------
# 1. DB 초기화 (기존 DB 구조 완전 마이그레이션)
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1) 학생 명단 테이블 구조 검사 (grade, class_name, student_id 복합 PK 미적용 시 재생성)
    c.execute("PRAGMA table_info(student_list)")
    s_cols_info = c.fetchall()
    if len(s_cols_info) > 0:
        s_pk_count = sum([1 for col in s_cols_info if col[5] > 0])
        # PK가 3개가 아닌 구버전 구조면 삭제 후 재 create (번호 중복 에러 방지)
        if s_pk_count < 3:
            c.execute("DROP TABLE student_list")

    c.execute('''
        CREATE TABLE IF NOT EXISTS student_list (
            grade TEXT,
            class_name TEXT,
            student_id TEXT,
            student_name TEXT,
            pin TEXT,
            PRIMARY KEY (grade, class_name, student_id)
        )
    ''')

    # 2) 독서 기록 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS reading_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT,
            class_name TEXT,
            student_id TEXT,
            student_name TEXT,
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

    # 3) 평가 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT,
            class_name TEXT,
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
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, book_title) ON CONFLICT REPLACE
        )
    ''')

    # 4) allowed_class_dates 테이블 PK 구조 검사 및 재생성
    c.execute("PRAGMA table_info(allowed_class_dates)")
    cols_info = c.fetchall()
    if len(cols_info) > 0:
        cols = [col[1] for col in cols_info]
        pk_count = sum([1 for col in cols_info if col[5] > 0])
        if 'grade' not in cols or pk_count < 3:
            c.execute("DROP TABLE allowed_class_dates")

    c.execute('''
        CREATE TABLE IF NOT EXISTS allowed_class_dates (
            grade TEXT,
            class_name TEXT,
            allowed_date TEXT,
            session_num TEXT,
            PRIMARY KEY (grade, class_name, allowed_date)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------
# 2. UI & 태블릿 최적화 CSS (정렬 보정 추가)
# -------------------------------------------------------------------
st.set_page_config(page_title="중학생 독서 포트폴리오", page_icon="📚", layout="wide")

st.markdown("""
    <style>
    /* 입력 위젯 간 높이 및 정렬 통일 */
    div[data-baseweb="select"], div[data-baseweb="input"] {
        margin-top: 0px !important;
    }
    .stSelectbox label, .stTextInput label {
        font-size: 15px !important;
        font-weight: 600 !important;
        min-height: 25px !important;
        display: flex;
        align-items: flex-end;
    }
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        font-size: 18px !important;
        border-radius: 10px !important;
    }
    .stButton button {
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 10px !important;
    }
    .card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ... (이전 코드 동일) ...

# -------------------------------------------------------------------
# 4. 학생용 화면 (입장 버튼 폼 적용)
# -------------------------------------------------------------------
if user_type == "👨‍🎓 학생용 (독서 기록)":
    st.title("📚 나의 독서 포트폴리오 (학생용)")
    
    # [수정] st.form을 활용하여 '입장' 버튼 생성 및 수평 정렬 맞춤
    with st.form("student_login_form"):
        st.markdown("##### 🔑 학생 로그인")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            grade = st.selectbox("학년 선택", ["1학년", "2학년", "3학년"], key="s_grade")
        with c2:
            class_name = st.selectbox("학반 선택", ["1반", "2반", "3반", "4반", "5반", "6반", "7반", "8반"], key="s_class")
        with c3:
            student_id = st.text_input("번호 (예: 15)", key="s_id")
        with c4:
            pin = st.text_input("지정 PIN 번호 4자리", type="password", key="s_pin")
        
        login_btn = st.form_submit_button("🚀 학생 포트폴리오 입장하기", use_container_width=True)

    # 입장 버튼을 눌렀을 때 검증 수행
    if login_btn:
        if not student_id or not pin:
            st.warning("⚠️ 번호와 PIN 번호를 모두 입력해 주세요.")
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT student_name FROM student_list WHERE grade = ? AND class_name = ? AND student_id = ? AND pin = ?", 
                      (grade, class_name, student_id, pin))
            user_match = c.fetchone()
            conn.close()

            if not user_match:
                st.error("❌ 학년, 학반, 번호 또는 비밀번호가 일치하지 않습니다. 선생님께 문의하세요.")
            else:
                st.session_state['logged_in_student'] = {
                    'grade': grade,
                    'class_name': class_name,
                    'student_id': student_id,
                    'student_name': user_match[0]
                }

    # 로그인 성공 상태 유지 시 포트폴리오 화면 표시
    if 'logged_in_student' in st.session_state:
        std_info = st.session_state['logged_in_student']
        s_grade = std_info['grade']
        s_class = std_info['class_name']
        s_id = std_info['student_id']
        s_name = std_info['student_name']

        st.success(f"👋 **[{s_grade} {s_class} {s_id}번] {s_name}** 학생 환영합니다!")

        today_str = date.today().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT session_num FROM allowed_class_dates WHERE grade = ? AND class_name = ? AND allowed_date = ?", 
                  (s_grade, s_class, today_str))
        date_record = c.fetchone()
        conn.close()

        tab1, tab2 = st.tabs(["📝 오늘의 독서 기록 쓰기", "📖 내 기록 모아보기"])

        with tab1:
            if not date_record:
                st.error(f"⛔ [{s_grade} {s_class}]은(는) 오늘({today_str}) 독서 기록 작성 허용 날짜가 아닙니다.")
                st.info(f"💡 선생님이 [{s_grade} {s_class}]의 독서 수업 날짜로 지정한 날에만 작성할 수 있습니다.")
            else:
                session_name = date_record[0]
                st.info(f"📌 **현재 진행 차시:** {s_grade} {s_class} - {session_name}")
                
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
                    summary = st.text_area("1. 오늘 읽은 내용 짧은 요약 (핵심 줄거리) *", height=120)
                    quote = st.text_area("2. 가장 인상 깊은 문장과 이유", height=100)
                    
                    st.markdown("#### ❓ 3. 질문 및 답변 작성")
                    col_q1, col_q2 = st.columns(2)
                    with col_q1:
                        question_text = st.text_area("3-1. 읽은 내용에 대한 나의 질문", height=110, placeholder="예: 주인공은 왜 그런 선택을 했을까?")
                    with col_q2:
                        answer_text = st.text_area("3-2. 질문에 대한 나의 생각/답변", height=110, placeholder="예: 자신의 목표를 이루기 위해 위험을 무릅쓴 것 같다.")
                    
                    reflection = st.text_area("4. 나의 생각과 느낌 (느낀점/깨달은점) *", height=140)

                    submit_btn = st.form_submit_button("🚀 독서 기록 제출하기")

                    if submit_btn:
                        if not book_title or not pages_read or not summary or not reflection:
                            st.error("필수 항목(책 제목, 페이지, 요약, 느낀점)을 빠짐없이 입력해 주세요!")
                        else:
                            # 질문과 답변을 하나의 문맥으로 병합하여 저장
                            combined_qa = f"Q: {question_text.strip()}\nA: {answer_text.strip()}" if (question_text or answer_text) else ""

                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO reading_logs 
                                (grade, class_name, student_id, student_name, book_title, author, log_date, pages_read, summary, quote, qa_pair, reflection)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (s_grade, s_class, s_id, s_name, book_title, author, today_str, pages_read, summary, quote, combined_qa, reflection))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.success("오늘의 독서 기록이 정상 제출되었습니다!")
        with tab2:
            st.markdown("#### 내 누적 포트폴리오")
            conn = sqlite3.connect(DB_FILE)
            df_my = pd.read_sql_query("SELECT * FROM reading_logs WHERE grade = ? AND class_name = ? AND student_id = ? ORDER BY id DESC", conn, params=(s_grade, s_class, s_id))
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
# 5. 교사용 화면
# -------------------------------------------------------------------
else:
    st.title("👩‍🏫 교사 관리 및 AI 자동 채점 시스템")
    teacher_pw = st.sidebar.text_input("교사 비밀번호", type="password")
    
    if teacher_pw != "0923":
        st.warning("교사전용 비밀번호를 입력해야 접근할 수 있습니다.")
    else:
        st.success("교사 인증이 완료되었습니다.")
        
        t_tab1, t_tab2, t_tab3, t_tab4 = st.tabs(["👨‍🎓 학생 명단 등록", "📅 학년/반/차시별 날짜 설정", "🤖 AI 자동 채점 & 검토", "📥 성적 집계 다운로드"])
        
        # Tab 1: 학생 명단 등록
        with t_tab1:
            st.markdown("### 👨‍🎓 학생 명단 사전 등록")
            st.caption("학생들이 접속 시 인증할 [학년, 학반, 번호, 이름, PIN 4자리] 명단을 등록합니다.")
            
            c_m1, c_m2 = st.columns([1, 1])
            with c_m1:
                st.markdown("#### 📄 엑셀 / CSV 파일로 일괄 업로드")
                st.caption("양식 열 이름: `grade` (예: 1학년), `class_name` (예: 1반), `student_id` (예: 15), `student_name`, `pin`")
                uploaded_file = st.file_uploader("명단 파일(CSV/Excel) 선택", type=["csv", "xlsx"])
                if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith('.csv'):
                            df_upload = pd.read_csv(uploaded_file, dtype=str)
                        else:
                            df_upload = pd.read_excel(uploaded_file, dtype=str)
                        
                        conn = sqlite3.connect(DB_FILE)
                        for _, r in df_upload.iterrows():
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO student_list (grade, class_name, student_id, student_name, pin)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(grade, class_name, student_id) DO UPDATE SET 
                                student_name=excluded.student_name, pin=excluded.pin
                            ''', (str(r['grade']), str(r['class_name']), str(r['student_id']), str(r['student_name']), str(r['pin'])))
                        conn.commit()
                        conn.close()
                        st.success("명단 일괄 업로드가 완료되었습니다!")
                    except Exception as e:
                        st.error(f"업로드 중 오류 발생: {e}")

                st.markdown("---")
                st.markdown("#### ✏️ 개별 직접 추가")
                with st.form("single_student_form"):
                    s_grade = st.selectbox("학년", ["1학년", "2학년", "3학년"])
                    s_class = st.selectbox("학반", ["1반", "2반", "3반", "4반", "5반", "6반", "7반", "8반"])
                    s_id = st.text_input("번호 (예: 15)")
                    s_name = st.text_input("이름")
                    s_pin = st.text_input("초기 비밀번호 4자리")
                    
                    if st.form_submit_button("학생 추가하기"):
                        if s_id and s_name and s_pin:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO student_list (grade, class_name, student_id, student_name, pin)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(grade, class_name, student_id) DO UPDATE SET 
                                student_name=excluded.student_name, pin=excluded.pin
                            ''', (s_grade, s_class, s_id, s_name, s_pin))
                            conn.commit()
                            conn.close()
                            st.success(f"{s_name} 학생이 등록되었습니다.")

            with c_m2:
                st.markdown("#### 📋 현재 등록된 학생 명단")
                conn = sqlite3.connect(DB_FILE)
                df_std = pd.read_sql_query("SELECT grade AS 학년, class_name AS 학반, student_id AS 번호, student_name AS 이름, pin AS 비밀번호 FROM student_list ORDER BY grade ASC, class_name ASC, CAST(student_id AS INTEGER) ASC", conn)
                conn.close()
                st.dataframe(df_std, use_container_width=True)

        # Tab 2: 학년/학반별 허용 날짜 설정
        with t_tab2:
            st.markdown("### 📅 학년/학반별 차시 독서 작성 허용 날짜 지정")
            col_d1, col_d2 = st.columns([1, 1])
            with col_d1:
                with st.form("add_class_date_form"):
                    target_grade = st.selectbox("학년 선택", ["1학년", "2학년", "3학년"])
                    target_class = st.selectbox("학반 선택", ["1반", "2반", "3반", "4반", "5반", "6반", "7반", "8반"])
                    session_num = st.selectbox("차시 선택", [f"{i}차시" for i in range(1, 18)])
                    target_date = st.date_input("작성 허용 날짜 지정", date.today()).strftime("%Y-%m-%d")
                    
                    submit_date = st.form_submit_button("➕ 날짜 허용 등록")
                    if submit_date:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO allowed_class_dates (grade, class_name, allowed_date, session_num)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(grade, class_name, allowed_date) DO UPDATE SET session_num=excluded.session_num
                        ''', (target_grade, target_class, target_date, session_num))
                        conn.commit()
                        conn.close()
                        st.success(f"[{target_grade} {target_class}] {session_num} - {target_date} 설정 완료!")

            with col_d2:
                conn = sqlite3.connect(DB_FILE)
                allowed_df = pd.read_sql_query("""
                    SELECT grade AS 학년, class_name AS 학반, session_num AS 차시, allowed_date AS 작성허용날짜 
                    FROM allowed_class_dates ORDER BY grade ASC, class_name ASC, allowed_date DESC
                """, conn)
                conn.close()
                st.dataframe(allowed_df, use_container_width=True)

        # Tab 3: AI 자동 채점
        with t_tab3:
            st.markdown("### 🤖 GPT AI 기반 루브릭 자동 채점")
            api_key = st.text_input("OpenAI API Key 입력", type="password")
            
            conn = sqlite3.connect(DB_FILE)
            df_all = pd.read_sql_query("SELECT * FROM reading_logs ORDER BY grade ASC, class_name ASC, CAST(student_id AS INTEGER) ASC", conn)
            conn.close()
            
            if df_all.empty:
                st.info("제출된 독서 기록이 없습니다.")
            else:
                df_all['user_label'] = df_all.apply(lambda r: f"[{r['grade']} {r['class_name']}] {r['student_id']}번 - {r['student_name']}", axis=1)
                unique_students = df_all[['grade', 'class_name', 'student_id', 'user_label']].drop_duplicates()
                
                sel_label = st.selectbox("학생 선택", unique_students['user_label'].tolist())
                sel_info = unique_students[unique_students['user_label'] == sel_label].iloc[0]
                
                s_logs = df_all[(df_all['grade'] == sel_info['grade']) & (df_all['class_name'] == sel_info['class_name']) & (df_all['student_id'] == sel_info['student_id'])]
                s_name = sel_info['user_label']
                sel_book = st.selectbox("책 선택", s_logs['book_title'].unique())
                
                target_logs = s_logs[s_logs['book_title'] == sel_book]
                
                combined_text = ""
                for _, r in target_logs.iterrows():
                    combined_text += f"\n[날짜: {r['log_date']}]\n- 요약: {r['summary']}\n- 문장: {r['quote']}\n- 질문답변: {r['qa_pair']}\n- 느낌: {r['reflection']}\n"
                
                col_ui1, col_ui2 = st.columns(2)
                with col_ui1:
                    st.markdown(f"#### 📖 {s_name} 누적 기록 (총 {len(target_logs)}회)")
                    st.text_area("전체 작성 내용", combined_text, height=400)
                
                with col_ui2:
                    st.markdown("#### 🤖 AI 채점 실행하기")
                    if st.button("✨ 루브릭 기준 AI 자동 채점 실행"):
                        if not api_key:
                            st.error("OpenAI API 키를 먼저 입력해 주세요!")
                        else:
                            with st.spinner("AI가 학생의 글을 분석하여 채점 중입니다..."):
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

        # Tab 4: 성적 집계 다운로드
        with t_tab4:
            st.markdown("#### 전체 성적표 내보내기")
            conn = sqlite3.connect(DB_FILE)
            df_eval_all = pd.read_sql_query("SELECT * FROM evaluations", conn)
            conn.close()
            st.dataframe(df_eval_all, use_container_width=True)
