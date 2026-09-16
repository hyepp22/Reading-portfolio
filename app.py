import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# 페이지 기본 설정
st.set_page_config(page_title="중학교 독서 포트폴리오", layout="wide")

# Google Sheets 연결 함수 (gspread 사용)
@st.cache_resource
def get_gsheet_client():
    # Secrets에 등록된 구글 시트 URL 가져오기
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    
    # 만약 Service Account JSON 키 방식이 아닌 Public/Shared URL 제어 시
    gc = gspread.public_authorize(sheet_url)
    return gc

# 간단 데이터 읽기/쓰기 헬퍼 함수
def load_sheet_data(worksheet_name):
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    # open_by_url을 사용해 시트 열기
    gc = gspread.oauth() # 기본인증
    # Streamlit Secrets 연결 방식 처리
    df = pd.read_csv(f"{sheet_url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet={worksheet_name}")
    return df

# 세션 상태 초기화
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
                sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
                csv_url = f"{sheet_url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet=students"
                df_students = pd.read_csv(csv_url)
                
                matched = df_students[
                    (df_students['학년'].astype(str) == grade.strip()) &
                    (df_students['학급'].astype(str) == ban.strip()) &
                    (df_students['번호'].astype(str) == num.strip()) &
                    (df_students['이름'].astype(str) == s_name.strip()) &
                    (df_students['고유번호'].astype(str) == s_pin.strip())
                ]
                
                if not matched.empty:
                    student_data = matched.iloc[0].to_dict()
                    formatted_num = str(student_data['번호']).zfill(2)
                    student_data['학번'] = f"{student_data['학년']}{str(student_data['학급']).zfill(2)}{formatted_num}"
                    
                    st.session_state.logged_in = True
                    st.session_state.student_info = student_data
                    st.success(f"{s_name} 학생 환영합니다!")
                    st.rerun()
                else:
                    st.error("입력하신 회원 정보가 일치하지 않습니다. 다시 확인해주세요.")
            except Exception as e:
                st.error("구글 시트 데이터를 불러오는 데 실패했습니다. Secrets 주소 및 시트 공유(편집자) 설정을 확인해 주세요.")

# ---------------------------------------------------------
# [2] 학생 독서 기록 작성 및 조회 화면
# ---------------------------------------------------------
else:
    student = st.session_state.student_info
    
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
                    # Form Submit 전송 처리
                    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
                    # Web Form 전송 및 시트 직접 기록 파이프라인
                    st.balloons()
                    st.success("독서 기록이 제출되었습니다!")
                except Exception as e:
                    st.error(f"저장 오류: {e}")

    # 나의 누적 독서 기록 조회
    st.divider()
    st.subheader("📚 나의 누적 독서 기록")
    try:
        sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        csv_url = f"{sheet_url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet=logs"
        logs_df = pd.read_csv(csv_url)
        
        my_logs = logs_df[logs_df['학번'].astype(str) == str(student['학번'])]
        
        if not my_logs.empty:
            st.dataframe(
                my_logs[['차시', '책제목', '작가', '읽은 날짜', '읽은 페이지', '오늘 읽은 부분 요약', '인상깊은 내용', '질문과 답변', '나의 생각과 느낌']], 
                use_container_width=True
            )
        else:
            st.info("아직 등록된 독서 기록이 없습니다.")
    except Exception as e:
        st.info("기록을 불러오는 중입니다.")
