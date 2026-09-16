import streamlit as st
from streamlit.connections import GSheetsConnection
import pandas as pd
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# Google Sheets 연결 (Streamlit 내장 커넥터 사용)
conn = st.connection("gsheets", type=GSheetsConnection)

# 세션 상태 초기화 (로그인 상태 유지)
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.student_info = None

# ---------------------------------------------------------
# [1] 로그인 화면
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.title("📚 중학교 독서 포트폴리오 로그인")
    st.caption("학년, 학급, 번호, 이름, 고유번호를 정확히 입력하세요.")
    
    with st.form("login_form"):
        col_grade, col_class, col_num = st.columns(3)
        with col_grade:
            grade = st.text_input("학년 (예: 2)")
        with col_class:
            ban = st.text_input("학급 (예: 3)")
        with col_num:
            num = st.text_input("번호 (예: 15)")
            
        s_name = st.text_input("이름 (예: 홍길동)")
        s_pin = st.text_input("고유번호 (4자리 PIN)", type="password")
        
        submit = st.form_submit_button("로그인")
        
        if submit:
            try:
                # 'students' 시트에서 데이터 불러오기
                df_students = conn.read(worksheet="students", ttl=0)
                
                # 학생 입력 정보 일치 확인
                matched = df_students[
                    (df_students['학년'].astype(str) == grade.strip()) &
                    (df_students['학급'].astype(str) == ban.strip()) &
                    (df_students['번호'].astype(str) == num.strip()) &
                    (df_students['이름'].astype(str) == s_name.strip()) &
                    (df_students['고유번호'].astype(str) == s_pin.strip())
                ]
                
                if not matched.empty:
                    student_data = matched.iloc[0].to_dict()
                    
                    # 학번 자동 생성 (예: 2학년 3반 15번 -> 20315 형식)
                    formatted_num = str(student_data['번호']).zfill(2)
                    student_data['학번'] = f"{student_data['학년']}{str(student_data['학급']).zfill(2)}{formatted_num}"
                    
                    st.session_state.logged_in = True
                    st.session_state.student_info = student_data
                    st.success(f"{s_name} 학생 환영합니다!")
                    st.rerun()
                else:
                    st.error("입력하신 회원 정보가 일치하지 않습니다. 다시 확인해주세요.")
            except Exception as e:
                st.error("구글 스프레드시트에 접근할 수 없습니다. Secrets 설정 및 시트 공유 설정을 확인해주세요.")

# ---------------------------------------------------------
# [2] 학생 독서 기록 작성 및 조회 화면
# ---------------------------------------------------------
else:
    student = st.session_state.student_info
    
    # 상단 학생 정보 및 로그아웃 버튼
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"📖 {student['이름']} 학생의 독서 포트폴리오")
        st.write(f"**소속:** {student['학년']}학년 {student['학급']}반 {student['번호']}번 (학번: {student['학번']})")
    with col2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.student_info = None
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
        summary = st.text_area("1. 오늘 읽은 부분 요약 *", help="핵심 내용을 간략히 정리해 보세요.")
        quote = st.text_area("2. 인상깊은 내용 *", help="가장 기억에 남는 문장이나 장면을 적어보세요.")
        q_na = st.text_area("3. 질문과 답변 *", help="읽은 부분에 대한 스스로의 질문과 답변을 적어보세요.")
        thought = st.text_area("4. 나의 생각과 느낌 *", help="읽고 느낀 점이나 내 삶과 관련지어 작성해 보세요.")

        submitted = st.form_submit_button("📌 독서 기록 제출하기")
        
        if submitted:
            if not (book_title and author and summary and quote and q_na and thought):
                st.warning("모든 필수 항목(*)을 작성해 주세요.")
            else:
                try:
                    # 구글 스프레드시트 'logs' 시트 헤더와 매핑되는 데이터 프레임 생성
                    new_data = pd.DataFrame([{
                        "학번": student['학번'],
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
                    
                    # 기존 데이터를 읽어와 병합 후 'logs' 시트에 업데이트
                    existing_data = conn.read(worksheet="logs", ttl=0)
                    updated_df = pd.concat([existing_data, new_data], ignore_index=True)
                    conn.update(worksheet="logs", data=updated_df)
                    
                    st.balloons()
                    st.success("독서 기록이 구글 스프레드시트에 성공적으로 저장되었습니다!")
                except Exception as e:
                    st.error(f"저장 중 오류가 발생했습니다: {e}")

    # 나의 누적 독서 기록 조회
    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    try:
        logs_df = conn.read(worksheet="logs", ttl=0)
        
        # 학번으로 내 기록 필터링
        my_logs = logs_df[logs_df['학번'].astype(str) == str(student['학번'])]
        
        if not my_logs.empty:
            st.dataframe(
                my_logs[['차시', '책제목', '작가', '읽은 날짜', '읽은 페이지', '오늘 읽은 부분 요약', '인상깊은 내용', '질문과 답변', '나의 생각과 느낌']], 
                use_container_width=True
            )
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")
    except Exception as e:
        st.warning("누적 기록을 불러오는 중입니다...")
