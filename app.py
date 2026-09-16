import streamlit as st
import pandas as pd
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# Google Sheets 연결 (Streamlit 커넥터 사용)
from streamlit_gsheets import GSheetsConnection
conn = st.connection("gsheets", type=GSheetsConnection)

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
                grade = st.text_input("학년 (예: 2)")
            with col_c:
                ban = st.text_input("학급 (예: 3)")
            with col_n:
                num = st.text_input("번호 (예: 1)")
                
            s_name = st.text_input("이름")
            s_pin = st.text_input("고유번호 (4자리 PIN)", type="password")
            
            submit_student = st.form_submit_button("학생 로그인")
            
            if submit_student:
                try:
                    df_students = conn.read(worksheet="students", ttl=0)
                    matched = df_students[
                        (df_students['학년'].astype(str) == grade.strip()) &
                        (df_students['학급'].astype(str) == ban.strip()) &
                        (df_students['번호'].astype(str) == num.strip()) &
                        (df_students['이름'].astype(str) == s_name.strip()) &
                        (df_students['고유번호'].astype(str) == s_pin.strip())
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
                        st.error("입력한 회원 정보가 일치하지 않습니다.")
                except Exception as e:
                    st.error(f"데이터 연결 오류: {e}")

    # 1-2. 교사 로그인
    with tab_teacher:
        with st.form("teacher_login_form"):
            teacher_pin = st.text_input("교사 관리자 비밀번호", type="password", help="기본 비밀번호: teacher1234")
            submit_teacher = st.form_submit_button("관리자 로그인")
            
            if submit_teacher:
                if teacher_pin == "teacher1234":  # 필요 시 교사 비밀번호 변경 가능
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

    # 독서 기록 입력 폼
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
                try:
                    new_data = pd.DataFrame([{
                        "학번": str(student['학번']),
                        "작성일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "이름": student['이름'],
                        "책제목": book_title,
                        "작가": author,
                        "차시": session_num,
                        "읽은 날짜": str(read_date),
                        "읽은 페이지": pages,
                        "오늘 읽은 부분 요약": summary,
                        "인상깊은 내용": quote,
                        "질문과 답변": q_na,
                        "나의 생각과 느낌": thought
                    }])
                    
                    existing_data = conn.read(worksheet="logs", ttl=0)
                    updated_df = pd.concat([existing_data, new_data], ignore_index=True)
                    conn.update(worksheet="logs", data=updated_df)
                    
                    st.balloons()
                    st.success("독서 기록이 저장되었습니다!")
                except Exception as e:
                    st.error(f"저장 중 오류: {e}")

    # 누적 기록 조회
    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    try:
        logs_df = conn.read(worksheet="logs", ttl=0)
        my_logs = logs_df[logs_df['학번'].astype(str) == str(student['학번'])]
        if not my_logs.empty:
            st.dataframe(my_logs, use_container_width=True)
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")
    except Exception:
        st.info("기록을 불러오는 중입니다.")

# ---------------------------------------------------------
# [3] 교사 전용 관리자 화면 (요청하신 통합 대시보드)
# ---------------------------------------------------------
elif st.session_state.user_type == "teacher":
    # 상단 헤더
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.caption("🔵 교사 전용 모드 | 중학교 독서수행평가 및 15~17차시 진도 통합 관리 센터")
        st.title("학생별 독서 포트폴리오 진도 & 수행평가 채점")
    with col_t2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    # 데이터 로드
    try:
        df_students = conn.read(worksheet="students", ttl=0)
        df_logs = conn.read(worksheet="logs", ttl=0)
    except Exception as e:
        st.error("구글 시트 데이터를 로드하지 못했습니다.")
        st.stop()

    # 학급 선택 필터
    st.divider()
    grades = sorted(df_students['학년'].astype(str).unique())
    selected_grade = st.sidebar.selectbox("학년 선택", grades)
    
    classes = sorted(df_students[df_students['학년'].astype(str) == selected_grade]['학급'].astype(str).unique())
    selected_class = st.sidebar.selectbox("학급 선택", classes)

    # 해당 학급 학생 필터링
    class_students = df_students[
        (df_students['학년'].astype(str) == selected_grade) & 
        (df_students['학급'].astype(str) == selected_class)
    ].copy()

    # 학번 생성
    class_students['학번'] = class_students.apply(
        lambda r: f"{r['학년']}{str(r['학급']).zfill(2)}{str(r['번호']).zfill(2)}", axis=1
    )

    # 통계 계산
    total_students = len(class_students)
    
    # 4대 지표 카드 출력
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("👥 학급 전체 학생 수", f"{total_students} 명")
        st.caption("목표 15~17차시 독서 진행")
    with m2:
        st.metric("🟢 수행평가 채점 완료", "0 / 5명")
        st.caption("채점 진행률 0%")
    with m3:
        st.metric("📑 채점 대기 학생", f"{total_students} 명")
        st.caption("포트폴리오 검토 필요")
    with m4:
        st.metric("⚠️ 차시 누락 주의 학생", f"{total_students} 명")
        st.caption("독서 일지 작성 독려 권장")

    st.divider()

    # 학생별 독서 진도 매트릭스 표
    st.subheader(f"📌 {selected_grade}학년 {selected_class}반 학생별 독서 진도 매트릭스")
    
    search_query = st.text_input("🔍 학번 또는 이름 검색", "")

    for idx, student in class_students.iterrows():
        s_id = str(student['학번'])
        s_name = str(student['이름'])
        s_pin = str(student['고유번호'])
        
        if search_query and (search_query not in s_name and search_query not in s_id):
            continue

        # 해당 학생의 작성 기록 가져오기
        s_logs = df_logs[df_logs['학번'].astype(str) == s_id] if not df_logs.empty else pd.DataFrame()
        submitted_sessions = set(s_logs['차시'].dropna().tolist()) if not s_logs.empty else set()
        
        # 제출 차시 개수 (최대 16차시 기준 예시)
        submitted_count = len(submitted_sessions)
        
        # UI 레이아웃 구성
        row_c1, row_c2, row_c3, row_c4, row_c5 = st.columns([1.5, 2, 2.5, 1.5, 1.5])
        
        with row_c1:
            st.markdown(f"### **{student['번호']}번 {s_name}**")
            st.caption(f"학번 {s_id} (PIN: {s_pin})")
            
        with row_c2:
            if not s_logs.empty:
                books = s_logs['책제목'].unique()
                for b in books[:2]:
                    st.write(f"📖 《{b}》")
            else:
                st.caption("작성된 도서 없음")
                
        with row_c3:
            # 1~16차시 진도 블록 시각화
            blocks = ""
            missing_sessions = []
            for i in range(1, 17):
                sess_str = f"{i}차시"
                if sess_str in submitted_sessions:
                    blocks += f"🟩 "
                else:
                    blocks += f"⬜ "
                    missing_sessions.append(str(i))
            
            st.write(blocks)
            if missing_sessions:
                st.caption(f"🔻 누락: {', '.join(missing_sessions)}차시")
                
        with row_c4:
            st.write(f"**{submitted_count} / 16차시**")
            progress_pct = int((submitted_count / 16) * 100)
            st.caption(f"진도율 {progress_pct}%")
            
        with row_c5:
            # 학생 포트폴리오 상세 열람 팝업 버튼
            if st.button("🎗️ 포트폴리오 열람", key=f"btn_{s_id}"):
                @st.dialog(f"{s_name} 학생의 독서 포트폴리오")
                def view_portfolio():
                    if not s_logs.empty:
                        st.dataframe(s_logs[['차시', '책제목', '읽은 날짜', '오늘 읽은 부분 요약', '나의 생각과 느낌']], use_container_width=True)
                    else:
                        st.write("제출된 독서 기록이 없습니다.")
                view_portfolio()
                
        st.markdown("---")
