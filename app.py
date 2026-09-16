import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import time

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# 구글 시트 데이터 읽기 헬퍼 함수 (캐시 우회 및 빈 행 완전 제거)
@st.cache_data(ttl=0)
def load_data(worksheet_name):
    try:
        sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        base_url = sheet_url.split('/edit')[0]
        # URL 뒤에 타임스탬프(_=timestamp)를 붙여 구글 서버 캐시까지 강제 우회
        csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={worksheet_name}&_={int(time.time())}"
        
        df = pd.read_csv(csv_url, dtype=str)
        df = df.fillna("").apply(lambda x: x.str.replace(r'\.0$', '', regex=True).str.strip())
        
        # 이름 또는 학번에 값이 있는 유효한 행만 필터링 (빈 행 완전 제거)
        if '이름' in df.columns:
            df = df[df['이름'] != ""]
        return df
    except Exception:
        return pd.DataFrame()

# 세션 상태 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_type = None  # 'student' 또는 'teacher'
    st.session_state.user_info = None

# ---------------------------------------------------------
# [1] 통합 로그인 화면 (학생 / 교사)
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.title("📚 중학교 독서 포트폴리오 및 수행평가 관리 시스템")
    
    tab_student, tab_teacher = st.tabs(["👨‍🎓 학생 로그인", "🧑‍🏫 교사 관리자 로그인"])
    
    # 1-1. 학생 로그인
    with tab_student:
        with st.form("student_login_form"):
            col_g, col_c, col_n = st.columns(3)
            with col_g:
                grade = st.text_input("학년 (예: 1)")
            with col_c:
                ban = st.text_input("학급 (예: 1)")
            with col_n:
                num = st.text_input("번호 (예: 1)")
                
            s_name = st.text_input("이름 (예: 박은혜)")
            s_pin = st.text_input("고유번호 (예: 1234)", type="password")
            
            submit_student = st.form_submit_button("학생 로그인")
            
            if submit_student:
                df_students = load_data("students")
                
                if not df_students.empty:
                    matched = df_students[
                        (df_students['학년'] == grade.strip()) &
                        (df_students['학급'] == ban.strip()) &
                        (df_students['번호'] == num.strip()) &
                        (df_students['이름'] == s_name.strip()) &
                        (df_students['고유번호'] == s_pin.strip())
                    ]
                    
                    if not matched.empty:
                        student_data = matched.iloc[0].to_dict()
                        student_data['학번'] = f"{student_data['학년']}{str(student_data['학급']).zfill(2)}{str(student_data['번호']).zfill(2)}"
                        
                        st.session_state.logged_in = True
                        st.session_state.user_type = "student"
                        st.session_state.user_info = student_data
                        st.success(f"{s_name} 학생 환영합니다!")
                        st.rerun()
                    else:
                        st.error("입력한 회원 정보가 일치하지 않습니다. 학년, 학급, 번호, 이름, 고유번호를 확인하세요.")
                else:
                    st.error("등록된 학생 명단이 없거나 'students' 시트를 불러올 수 없습니다.")

    # 1-2. 교사 로그인
    with tab_teacher:
        with st.form("teacher_login_form"):
            TEACHER_PASSWORD = "teacher1234"  # 관리자 비밀번호
            teacher_pin = st.text_input("교사 관리자 비밀번호", type="password")
            submit_teacher = st.form_submit_button("관리자 로그인")
            
            if submit_teacher:
                if teacher_pin == TEACHER_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.user_type = "teacher"
                    st.session_state.user_info = {"name": "관리자 교사"}
                    st.success("교사 전용 모드로 로그인되었습니다.")
                    st.rerun()
                else:
                    st.error("교사 비밀번호가 일치하지 않습니다.")

# ---------------------------------------------------------
# [2] 학생 전용 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "student":
    student = st.session_state.user_info
    
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"📖 {student['이름']} 학생의 독서 포트폴리오")
        st.write(f"**소속:** {student['학년']}학년 {student['학급']}반 {student['번호']}번 (학번: {student['학번']})")
    with col2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.divider()

    st.subheader("📝 차시별 독서 기록 작성하기")
    with st.form("reading_log_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            book_title = st.text_input("책 제목 *")
            author = st.text_input("작가 *")
            session_num = st.selectbox("차시 *", [f"{i}차시" for i in range(1, 18)])
        with c2:
            read_date = st.date_input("읽은 날짜 *", datetime.today())
            pages = st.text_input("읽은 페이지 (예: 12p ~ 45p) *")

        st.markdown("---")
        summary = st.text_area("1. 오늘 읽은 부분 요약 *")
        quote = st.text_area("2. 인상깊은 내용 *")
        q_na = st.text_area("3. 질문과 답변 *")
        thought = st.text_area("4. 나의 생각과 느낌 *")

        submitted = st.form_submit_button("📌 독서 기록 제출하기")
        
        if submitted:
            if not (book_title and author and summary and quote and q_na and thought):
                st.warning("모든 필수 항목(*)을 작성해 주세요.")
            else:
                if "script_url" in st.secrets:
                    payload = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "student_id": student['학번'],
                        "name": student['이름'],
                        "session": session_num,
                        "book_title": book_title,
                        "author": author,
                        "read_date": str(read_date),
                        "pages": pages,
                        "summary": summary,
                        "quote": quote,
                        "q_na": q_na,
                        "thought": thought
                    }
                    try:
                        res = requests.post(st.secrets["script_url"], json=payload)
                        if res.status_code == 200:
                            st.balloons()
                            st.success("독서 기록이 구글 시트에 무사히 저장되었습니다!")
                        else:
                            st.error("구글 시트 전송 중 오류가 발생했습니다.")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")
                else:
                    st.warning("구글 시트 쓰기 연동(script_url) 설정이 되어있지 않습니다.")

    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    logs_df = load_data("logs")
    if not logs_df.empty:
        my_logs = logs_df[logs_df['학번'] == str(student['학번'])]
        if not my_logs.empty:
            st.dataframe(my_logs, use_container_width=True)
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")

# ---------------------------------------------------------
# [3] 교사 전용 관리자 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "teacher":
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.caption("🔵 교사 전용 모드 | 중학교 독서수행평가 및 진도 통합 관리 센터")
        st.title("학생별 독서 포트폴리오 진도 & 수행평가 대시보드")
    with col_t2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    df_students = load_data("students")
    df_logs = load_data("logs")

    if df_students.empty:
        st.info("현재 등록된 학생 명단이 없습니다. 구글 시트 'students' 탭을 확인하세요.")
        st.stop()

    st.divider()
    grades = sorted(df_students['학년'].unique())
    selected_grade = st.sidebar.selectbox("학년 선택", grades)
    
    classes = sorted(df_students[df_students['학년'] == selected_grade]['학급'].unique())
    selected_class = st.sidebar.selectbox("학급 선택", classes)

    class_students = df_students[
        (df_students['학년'] == selected_grade) & 
        (df_students['학급'] == selected_class)
    ].copy()

    class_students['학번'] = class_students.apply(
        lambda r: f"{r['학년']}{str(r['학급']).zfill(2)}{str(r['번호']).zfill(2)}", axis=1
    )

    total_students = len(class_students)
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("👥 학급 전체 학생 수", f"{total_students} 명")
    with m2:
        st.metric("🟢 수행평가 채점 완료", "0 명")
    with m3:
        st.metric("📑 채점 대기 학생", f"{total_students} 명")
    with m4:
        st.metric("⚠️ 차시 누락 주의 학생", f"{total_students} 명")

    st.divider()
    st.subheader(f"📌 {selected_grade}학년 {selected_class}반 학생별 독서 진도 매트릭스")

    for idx, student in class_students.iterrows():
        s_id = str(student['학번'])
        s_name = str(student['이름'])
        s_pin = str(student['고유번호'])
        
        s_logs = df_logs[df_logs['학번'] == s_id] if not df_logs.empty else pd.DataFrame()
        submitted_sessions = set(s_logs['차시'].tolist()) if not s_logs.empty else set()
        
        row_c1, row_c2, row_c3, row_c4 = st.columns([2, 2, 4, 2])
        
        with row_c1:
            st.markdown(f"**{student['번호']}번 {s_name}** (PIN: {s_pin})")
        with row_c2:
            if not s_logs.empty and '책제목' in s_logs.columns:
                st.write(f"📖 {s_logs['책제목'].iloc[0]}")
            else:
                st.caption("기록 없음")
        with row_c3:
            blocks = ""
            for i in range(1, 17):
                blocks += "🟩 " if f"{i}차시" in submitted_sessions else "⬜ "
            st.write(blocks)
        with row_c4:
            st.write(f"{len(submitted_sessions)} / 16 차시")
            
        st.markdown("---")import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import time

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# 구글 시트 데이터 읽기 헬퍼 함수 (캐시 우회 및 빈 행 완전 제거)
@st.cache_data(ttl=0)
def load_data(worksheet_name):
    try:
        sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        base_url = sheet_url.split('/edit')[0]
        # URL 뒤에 타임스탬프(_=timestamp)를 붙여 구글 서버 캐시까지 강제 우회
        csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={worksheet_name}&_={int(time.time())}"
        
        df = pd.read_csv(csv_url, dtype=str)
        df = df.fillna("").apply(lambda x: x.str.replace(r'\.0$', '', regex=True).str.strip())
        
        # 이름 또는 학번에 값이 있는 유효한 행만 필터링 (빈 행 완전 제거)
        if '이름' in df.columns:
            df = df[df['이름'] != ""]
        return df
    except Exception:
        return pd.DataFrame()

# 세션 상태 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_type = None  # 'student' 또는 'teacher'
    st.session_state.user_info = None

# ---------------------------------------------------------
# [1] 통합 로그인 화면 (학생 / 교사)
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.title("📚 중학교 독서 포트폴리오 및 수행평가 관리 시스템")
    
    tab_student, tab_teacher = st.tabs(["👨‍🎓 학생 로그인", "🧑‍🏫 교사 관리자 로그인"])
    
    # 1-1. 학생 로그인
    with tab_student:
        with st.form("student_login_form"):
            col_g, col_c, col_n = st.columns(3)
            with col_g:
                grade = st.text_input("학년 (예: 1)")
            with col_c:
                ban = st.text_input("학급 (예: 1)")
            with col_n:
                num = st.text_input("번호 (예: 1)")
                
            s_name = st.text_input("이름 (예: 박은혜)")
            s_pin = st.text_input("고유번호 (예: 1234)", type="password")
            
            submit_student = st.form_submit_button("학생 로그인")
            
            if submit_student:
                df_students = load_data("students")
                
                if not df_students.empty:
                    matched = df_students[
                        (df_students['학년'] == grade.strip()) &
                        (df_students['학급'] == ban.strip()) &
                        (df_students['번호'] == num.strip()) &
                        (df_students['이름'] == s_name.strip()) &
                        (df_students['고유번호'] == s_pin.strip())
                    ]
                    
                    if not matched.empty:
                        student_data = matched.iloc[0].to_dict()
                        student_data['학번'] = f"{student_data['학년']}{str(student_data['학급']).zfill(2)}{str(student_data['번호']).zfill(2)}"
                        
                        st.session_state.logged_in = True
                        st.session_state.user_type = "student"
                        st.session_state.user_info = student_data
                        st.success(f"{s_name} 학생 환영합니다!")
                        st.rerun()
                    else:
                        st.error("입력한 회원 정보가 일치하지 않습니다. 학년, 학급, 번호, 이름, 고유번호를 확인하세요.")
                else:
                    st.error("등록된 학생 명단이 없거나 'students' 시트를 불러올 수 없습니다.")

    # 1-2. 교사 로그인
    with tab_teacher:
        with st.form("teacher_login_form"):
            TEACHER_PASSWORD = "teacher1234"  # 관리자 비밀번호
            teacher_pin = st.text_input("교사 관리자 비밀번호", type="password")
            submit_teacher = st.form_submit_button("관리자 로그인")
            
            if submit_teacher:
                if teacher_pin == TEACHER_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.user_type = "teacher"
                    st.session_state.user_info = {"name": "관리자 교사"}
                    st.success("교사 전용 모드로 로그인되었습니다.")
                    st.rerun()
                else:
                    st.error("교사 비밀번호가 일치하지 않습니다.")

# ---------------------------------------------------------
# [2] 학생 전용 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "student":
    student = st.session_state.user_info
    
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"📖 {student['이름']} 학생의 독서 포트폴리오")
        st.write(f"**소속:** {student['학년']}학년 {student['학급']}반 {student['번호']}번 (학번: {student['학번']})")
    with col2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.divider()

    st.subheader("📝 차시별 독서 기록 작성하기")
    with st.form("reading_log_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            book_title = st.text_input("책 제목 *")
            author = st.text_input("작가 *")
            session_num = st.selectbox("차시 *", [f"{i}차시" for i in range(1, 18)])
        with c2:
            read_date = st.date_input("읽은 날짜 *", datetime.today())
            pages = st.text_input("읽은 페이지 (예: 12p ~ 45p) *")

        st.markdown("---")
        summary = st.text_area("1. 오늘 읽은 부분 요약 *")
        quote = st.text_area("2. 인상깊은 내용 *")
        q_na = st.text_area("3. 질문과 답변 *")
        thought = st.text_area("4. 나의 생각과 느낌 *")

        submitted = st.form_submit_button("📌 독서 기록 제출하기")
        
        if submitted:
            if not (book_title and author and summary and quote and q_na and thought):
                st.warning("모든 필수 항목(*)을 작성해 주세요.")
            else:
                if "script_url" in st.secrets:
                    payload = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "student_id": student['학번'],
                        "name": student['이름'],
                        "session": session_num,
                        "book_title": book_title,
                        "author": author,
                        "read_date": str(read_date),
                        "pages": pages,
                        "summary": summary,
                        "quote": quote,
                        "q_na": q_na,
                        "thought": thought
                    }
                    try:
                        res = requests.post(st.secrets["script_url"], json=payload)
                        if res.status_code == 200:
                            st.balloons()
                            st.success("독서 기록이 구글 시트에 무사히 저장되었습니다!")
                        else:
                            st.error("구글 시트 전송 중 오류가 발생했습니다.")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")
                else:
                    st.warning("구글 시트 쓰기 연동(script_url) 설정이 되어있지 않습니다.")

    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    logs_df = load_data("logs")
    if not logs_df.empty:
        my_logs = logs_df[logs_df['학번'] == str(student['학번'])]
        if not my_logs.empty:
            st.dataframe(my_logs, use_container_width=True)
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")

# ---------------------------------------------------------
# [3] 교사 전용 관리자 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "teacher":
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.caption("🔵 교사 전용 모드 | 중학교 독서수행평가 및 진도 통합 관리 센터")
        st.title("학생별 독서 포트폴리오 진도 & 수행평가 대시보드")
    with col_t2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    df_students = load_data("students")
    df_logs = load_data("logs")

    if df_students.empty:
        st.info("현재 등록된 학생 명단이 없습니다. 구글 시트 'students' 탭을 확인하세요.")
        st.stop()

    st.divider()
    grades = sorted(df_students['학년'].unique())
    selected_grade = st.sidebar.selectbox("학년 선택", grades)
    
    classes = sorted(df_students[df_students['학년'] == selected_grade]['학급'].unique())
    selected_class = st.sidebar.selectbox("학급 선택", classes)

    class_students = df_students[
        (df_students['학년'] == selected_grade) & 
        (df_students['학급'] == selected_class)
    ].copy()

    class_students['학번'] = class_students.apply(
        lambda r: f"{r['학년']}{str(r['학급']).zfill(2)}{str(r['번호']).zfill(2)}", axis=1
    )

    total_students = len(class_students)
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("👥 학급 전체 학생 수", f"{total_students} 명")
    with m2:
        st.metric("🟢 수행평가 채점 완료", "0 명")
    with m3:
        st.metric("📑 채점 대기 학생", f"{total_students} 명")
    with m4:
        st.metric("⚠️ 차시 누락 주의 학생", f"{total_students} 명")

    st.divider()
    st.subheader(f"📌 {selected_grade}학년 {selected_class}반 학생별 독서 진도 매트릭스")

    for idx, student in class_students.iterrows():
        s_id = str(student['학번'])
        s_name = str(student['이름'])
        s_pin = str(student['고유번호'])
        
        s_logs = df_logs[df_logs['학번'] == s_id] if not df_logs.empty else pd.DataFrame()
        submitted_sessions = set(s_logs['차시'].tolist()) if not s_logs.empty else set()
        
        row_c1, row_c2, row_c3, row_c4 = st.columns([2, 2, 4, 2])
        
        with row_c1:
            st.markdown(f"**{student['번호']}번 {s_name}** (PIN: {s_pin})")
        with row_c2:
            if not s_logs.empty and '책제목' in s_logs.columns:
                st.write(f"📖 {s_logs['책제목'].iloc[0]}")
            else:
                st.caption("기록 없음")
        with row_c3:
            blocks = ""
            for i in range(1, 17):
                blocks += "🟩 " if f"{i}차시" in submitted_sessions else "⬜ "
            st.write(blocks)
        with row_c4:
            st.write(f"{len(submitted_sessions)} / 16 차시")
            
        st.markdown("---")import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import time

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# 구글 시트 데이터 읽기 헬퍼 함수 (캐시 우회 및 빈 행 완전 제거)
@st.cache_data(ttl=0)
def load_data(worksheet_name):
    try:
        sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        base_url = sheet_url.split('/edit')[0]
        # URL 뒤에 타임스탬프(_=timestamp)를 붙여 구글 서버 캐시까지 강제 우회
        csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={worksheet_name}&_={int(time.time())}"
        
        df = pd.read_csv(csv_url, dtype=str)
        df = df.fillna("").apply(lambda x: x.str.replace(r'\.0$', '', regex=True).str.strip())
        
        # 이름 또는 학번에 값이 있는 유효한 행만 필터링 (빈 행 완전 제거)
        if '이름' in df.columns:
            df = df[df['이름'] != ""]
        return df
    except Exception:
        return pd.DataFrame()

# 세션 상태 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_type = None  # 'student' 또는 'teacher'
    st.session_state.user_info = None

# ---------------------------------------------------------
# [1] 통합 로그인 화면 (학생 / 교사)
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.title("📚 중학교 독서 포트폴리오 및 수행평가 관리 시스템")
    
    tab_student, tab_teacher = st.tabs(["👨‍🎓 학생 로그인", "🧑‍🏫 교사 관리자 로그인"])
    
    # 1-1. 학생 로그인
    with tab_student:
        with st.form("student_login_form"):
            col_g, col_c, col_n = st.columns(3)
            with col_g:
                grade = st.text_input("학년 (예: 1)")
            with col_c:
                ban = st.text_input("학급 (예: 1)")
            with col_n:
                num = st.text_input("번호 (예: 1)")
                
            s_name = st.text_input("이름 (예: 박은혜)")
            s_pin = st.text_input("고유번호 (예: 1234)", type="password")
            
            submit_student = st.form_submit_button("학생 로그인")
            
            if submit_student:
                df_students = load_data("students")
                
                if not df_students.empty:
                    matched = df_students[
                        (df_students['학년'] == grade.strip()) &
                        (df_students['학급'] == ban.strip()) &
                        (df_students['번호'] == num.strip()) &
                        (df_students['이름'] == s_name.strip()) &
                        (df_students['고유번호'] == s_pin.strip())
                    ]
                    
                    if not matched.empty:
                        student_data = matched.iloc[0].to_dict()
                        student_data['학번'] = f"{student_data['학년']}{str(student_data['학급']).zfill(2)}{str(student_data['번호']).zfill(2)}"
                        
                        st.session_state.logged_in = True
                        st.session_state.user_type = "student"
                        st.session_state.user_info = student_data
                        st.success(f"{s_name} 학생 환영합니다!")
                        st.rerun()
                    else:
                        st.error("입력한 회원 정보가 일치하지 않습니다. 학년, 학급, 번호, 이름, 고유번호를 확인하세요.")
                else:
                    st.error("등록된 학생 명단이 없거나 'students' 시트를 불러올 수 없습니다.")

    # 1-2. 교사 로그인
    with tab_teacher:
        with st.form("teacher_login_form"):
            TEACHER_PASSWORD = "teacher1234"  # 관리자 비밀번호
            teacher_pin = st.text_input("교사 관리자 비밀번호", type="password")
            submit_teacher = st.form_submit_button("관리자 로그인")
            
            if submit_teacher:
                if teacher_pin == TEACHER_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.user_type = "teacher"
                    st.session_state.user_info = {"name": "관리자 교사"}
                    st.success("교사 전용 모드로 로그인되었습니다.")
                    st.rerun()
                else:
                    st.error("교사 비밀번호가 일치하지 않습니다.")

# ---------------------------------------------------------
# [2] 학생 전용 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "student":
    student = st.session_state.user_info
    
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"📖 {student['이름']} 학생의 독서 포트폴리오")
        st.write(f"**소속:** {student['학년']}학년 {student['학급']}반 {student['번호']}번 (학번: {student['학번']})")
    with col2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.divider()

    st.subheader("📝 차시별 독서 기록 작성하기")
    with st.form("reading_log_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            book_title = st.text_input("책 제목 *")
            author = st.text_input("작가 *")
            session_num = st.selectbox("차시 *", [f"{i}차시" for i in range(1, 18)])
        with c2:
            read_date = st.date_input("읽은 날짜 *", datetime.today())
            pages = st.text_input("읽은 페이지 (예: 12p ~ 45p) *")

        st.markdown("---")
        summary = st.text_area("1. 오늘 읽은 부분 요약 *")
        quote = st.text_area("2. 인상깊은 내용 *")
        q_na = st.text_area("3. 질문과 답변 *")
        thought = st.text_area("4. 나의 생각과 느낌 *")

        submitted = st.form_submit_button("📌 독서 기록 제출하기")
        
        if submitted:
            if not (book_title and author and summary and quote and q_na and thought):
                st.warning("모든 필수 항목(*)을 작성해 주세요.")
            else:
                if "script_url" in st.secrets:
                    payload = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "student_id": student['학번'],
                        "name": student['이름'],
                        "session": session_num,
                        "book_title": book_title,
                        "author": author,
                        "read_date": str(read_date),
                        "pages": pages,
                        "summary": summary,
                        "quote": quote,
                        "q_na": q_na,
                        "thought": thought
                    }
                    try:
                        res = requests.post(st.secrets["script_url"], json=payload)
                        if res.status_code == 200:
                            st.balloons()
                            st.success("독서 기록이 구글 시트에 무사히 저장되었습니다!")
                        else:
                            st.error("구글 시트 전송 중 오류가 발생했습니다.")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")
                else:
                    st.warning("구글 시트 쓰기 연동(script_url) 설정이 되어있지 않습니다.")

    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    logs_df = load_data("logs")
    if not logs_df.empty:
        my_logs = logs_df[logs_df['학번'] == str(student['학번'])]
        if not my_logs.empty:
            st.dataframe(my_logs, use_container_width=True)
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")

# ---------------------------------------------------------
# [3] 교사 전용 관리자 화면
# ---------------------------------------------------------
elif st.session_state.user_type == "teacher":
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.caption("🔵 교사 전용 모드 | 중학교 독서수행평가 및 진도 통합 관리 센터")
        st.title("학생별 독서 포트폴리오 진도 & 수행평가 대시보드")
    with col_t2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    df_students = load_data("students")
    df_logs = load_data("logs")

    if df_students.empty:
        st.info("현재 등록된 학생 명단이 없습니다. 구글 시트 'students' 탭을 확인하세요.")
        st.stop()

    st.divider()
    grades = sorted(df_students['학년'].unique())
    selected_grade = st.sidebar.selectbox("학년 선택", grades)
    
    classes = sorted(df_students[df_students['학년'] == selected_grade]['학급'].unique())
    selected_class = st.sidebar.selectbox("학급 선택", classes)

    class_students = df_students[
        (df_students['학년'] == selected_grade) & 
        (df_students['학급'] == selected_class)
    ].copy()

    class_students['학번'] = class_students.apply(
        lambda r: f"{r['학년']}{str(r['학급']).zfill(2)}{str(r['번호']).zfill(2)}", axis=1
    )

    total_students = len(class_students)
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("👥 학급 전체 학생 수", f"{total_students} 명")
    with m2:
        st.metric("🟢 수행평가 채점 완료", "0 명")
    with m3:
        st.metric("📑 채점 대기 학생", f"{total_students} 명")
    with m4:
        st.metric("⚠️ 차시 누락 주의 학생", f"{total_students} 명")

    st.divider()
    st.subheader(f"📌 {selected_grade}학년 {selected_class}반 학생별 독서 진도 매트릭스")

    for idx, student in class_students.iterrows():
        s_id = str(student['학번'])
        s_name = str(student['이름'])
        s_pin = str(student['고유번호'])
        
        s_logs = df_logs[df_logs['학번'] == s_id] if not df_logs.empty else pd.DataFrame()
        submitted_sessions = set(s_logs['차시'].tolist()) if not s_logs.empty else set()
        
        row_c1, row_c2, row_c3, row_c4 = st.columns([2, 2, 4, 2])
        
        with row_c1:
            st.markdown(f"**{student['번호']}번 {s_name}** (PIN: {s_pin})")
        with row_c2:
            if not s_logs.empty and '책제목' in s_logs.columns:
                st.write(f"📖 {s_logs['책제목'].iloc[0]}")
            else:
                st.caption("기록 없음")
        with row_c3:
            blocks = ""
            for i in range(1, 17):
                blocks += "🟩 " if f"{i}차시" in submitted_sessions else "⬜ "
            st.write(blocks)
        with row_c4:
            st.write(f"{len(submitted_sessions)} / 16 차시")
            
        st.markdown("---")
