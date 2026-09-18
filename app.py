import streamlit as st
import pandas as pd
from datetime import datetime, date
import openai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------------------------------------------------------
# 1. Google Sheets 연동 설정
# -------------------------------------------------------------------
# 구글 드라이브 스프레드시트 파일의 '제목'을 그대로 적어주세요.
SPREADSHEET_NAME = "중학교_독서포트폴리오_DB"

@st.cache_resource
def get_gspread_client():
    scope = [
        "[https://spreadsheets.google.com/feeds](https://spreadsheets.google.com/feeds)",
        "[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive)"
    ]
    # Secrets 값을 불러온 뒤 \n 문자열을 실제 줄바꿈으로 변경해 줍니다.
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# -------------------------------------------------------------------
# 2. UI 및 스타일 설정 (태블릿 최적화)
# -------------------------------------------------------------------
st.set_page_config(page_title="중학생 독서 포트폴리오", page_icon="📚", layout="wide")

st.markdown("""
    <style>
    div[data-baseweb="select"], div[data-baseweb="input"] { margin-top: 0px !important; }
    .stSelectbox label, .stTextInput label {
        font-size: 15px !important; font-weight: 600 !important;
        min-height: 25px !important; display: flex; align-items: flex-end;
    }
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        font-size: 17px !important; border-radius: 10px !important;
    }
    .stButton button {
        font-size: 18px !important; font-weight: bold !important; border-radius: 10px !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 3. 사이드바 - 사용자 모드 선택
# -------------------------------------------------------------------
st.sidebar.header("🔐 접속 모드")
user_type = st.sidebar.radio("모드를 선택하세요", ["👨‍🎓 학생용 (독서 기록)", "👩‍🏫 교사용 (관리 및 피드백)"])

# -------------------------------------------------------------------
# 4. 학생용 화면
# -------------------------------------------------------------------
if user_type == "👨‍🎓 학생용 (독서 기록)":
    st.title("📚 나의 독서 포트폴리오 (학생용)")
    
    # 4-1. 학생 로그인
    if 'logged_in_student' not in st.session_state:
        with st.form("student_login_form"):
            st.markdown("##### 🔑 학생 로그인")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                grade = st.selectbox("학년", ["1학년", "2학년", "3학년"], key="s_grade")
            with c2:
                class_name = st.selectbox("반", ["1반", "2반", "3반", "4반", "5반", "6반", "7반", "8반"], key="s_class")
            with c3:
                student_id = st.text_input("번호 (예: 15)", key="s_id")
            with c4:
                pin = st.text_input("고유번호 (PIN 4자리)", type="password", key="s_pin")
            
            login_btn = st.form_submit_button("🚀 학생 포트폴리오 입장하기", use_container_width=True)

        if login_btn:
            if not student_id or not pin:
                st.warning("⚠️ 번호와 고유번호를 모두 입력해 주세요.")
            else:
                try:
                    ws_std = get_worksheet("student_list")
                    df_std = pd.DataFrame(ws_std.get_all_records())
                    
                    # 한글 헤더 기준 데이터 검증 ('학년', '반', '번호', '고유번호', '이름')
                    user_match = df_std[
                        (df_std['학년'].astype(str) == str(grade)) &
                        (df_std['반'].astype(str) == str(class_name)) &
                        (df_std['번호'].astype(str) == str(student_id)) &
                        (df_std['고유번호'].astype(str) == str(pin))
                    ]

                    if user_match.empty:
                        st.error("❌ 학년, 반, 번호 또는 고유번호가 일치하지 않습니다. 선생님께 문의해 주세요.")
                    else:
                        st.session_state['logged_in_student'] = {
                            'grade': grade,
                            'class_name': class_name,
                            'student_id': student_id,
                            'student_name': user_match.iloc[0]['이름']
                        }
                        st.rerun()
                except Exception as e:
                    st.error(f"구글 시트 연결 오류: {e}")

    # 4-2. 로그인 성공 후 독서 기록 작성 화면
    else:
        std_info = st.session_state['logged_in_student']
        s_grade, s_class, s_id, s_name = std_info['grade'], std_info['class_name'], std_info['student_id'], std_info['student_name']

        c_top1, c_top2 = st.columns([4, 1])
        with c_top1:
            st.success(f"👋 **[{s_grade} {s_class} {s_id}번] {s_name}** 학생 환영합니다!")
        with c_top2:
            if st.button("로그아웃"):
                del st.session_state['logged_in_student']
                st.rerun()

        today_str = date.today().strftime("%Y-%m-%d")
        
        # 날짜 허용 시트 불러오기 (시트 이름: allowed_class_dates)
        # 만약 이 시트도 한글 헤더(학년, 반, 날짜, 차시)로 만드신 경우 자동 대응
        ws_dates = get_worksheet("allowed_class_dates")
        df_dates = pd.DataFrame(ws_dates.get_all_records())
        
        grade_col = '학년' if '학년' in df_dates.columns else 'grade'
        class_col = '반' if '반' in df_dates.columns else 'class_name'
        date_col = '날짜' if '날짜' in df_dates.columns else 'allowed_date'
        session_col = '차시' if '차시' in df_dates.columns else 'session_num'

        date_record = df_dates[
            (df_dates[grade_col].astype(str) == str(s_grade)) &
            (df_dates[class_col].astype(str) == str(s_class)) &
            (df_dates[date_col].astype(str) == str(today_str))
        ]

        tab1, tab2 = st.tabs(["📝 오늘의 독서 기록 쓰기", "📖 내 과거 기록 보기"])

        with tab1:
            if date_record.empty:
                st.error(f"⛔ [{s_grade} {s_class}]은(는) 오늘({today_str}) 독서 기록 작성 허용 날짜가 아닙니다.")
            else:
                session_name = date_record.iloc[0][session_col]
                st.info(f"📌 **현재 진행 차시:** {s_grade} {s_class} - {session_name}")
                
                with st.form("reading_form"):
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        book_title = st.text_input("책 제목 *")
                        author = st.text_input("작가 이름 *")
                    with col_b2:
                        pages_read = st.text_input("오늘 읽은 페이지 범위 (예: 12~35p) *")
                    
                    summary = st.text_area("1. 오늘 읽은 내용 짧은 요약 (핵심 줄거리) *", height=110)
                    quote = st.text_area("2. 가장 인상 깊은 문장과 이유", height=90)
                    
                    st.markdown("##### 3. 읽은 내용을 바탕으로 만든 질문과 답변")
                    col_q1, col_q2 = st.columns(2)
                    with col_q1:
                        question_text = st.text_area("3-1. 나의 질문", height=100, placeholder="예: 주인공은 왜 그런 선택을 했을까?")
                    with col_q2:
                        answer_text = st.text_area("3-2. 질문에 대한 나의 생각/답변", height=100, placeholder="예: 자신의 가치관을 지키기 위해서였을 것이다.")
                    
                    reflection = st.text_area("4. 나의 생각과 느낌 (느낀점/깨달은점) *", height=130)

                    submit_btn = st.form_submit_button("🚀 독서 기록 제출하기", use_container_width=True)

                    if submit_btn:
                        if not book_title or not pages_read or not summary or not reflection:
                            st.error("필수 항목(*)을 빠짐없이 입력해 주세요!")
                        else:
                            ws_logs = get_worksheet("reading_logs")
                            
                            # 구글 시트에 순서대로 한 행 추가 (A~N열 한글 헤더와 1:1 대응)
                            ws_logs.append_row([
                                str(s_grade),         # A: 학년
                                str(s_class),         # B: 반
                                str(s_id),            # C: 번호
                                str(s_name),          # D: 이름
                                book_title,           # E: 책 제목
                                author,               # F: 작가
                                today_str,            # G: 날짜
                                pages_read,           # H: 읽은 페이지
                                summary,              # I: 요약
                                quote,                # J: 인상깊은 내용
                                question_text,        # K: 질문
                                answer_text,          # L: 답변
                                reflection,           # M: 느낀점
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S") # N: 생성일시
                            ])
                            st.balloons()
                            st.success("오늘의 독서 기록이 구글 시트에 안전하게 제출되었습니다!")

        with tab2:
            ws_logs = get_worksheet("reading_logs")
            df_logs = pd.DataFrame(ws_logs.get_all_records())
            
            if not df_logs.empty:
                my_logs = df_logs[
                    (df_logs['학년'].astype(str) == str(s_grade)) &
                    (df_logs['반'].astype(str) == str(s_class)) &
                    (df_logs['번호'].astype(str) == str(s_id))
                ]
                if my_logs.empty:
                    st.info("아직 제출된 기록이 없습니다.")
                else:
                    for idx, row in my_logs.iterrows():
                        with st.expander(f"📌 [{row['날짜']}] {row['책 제목']} ({row['읽은 페이지']})"):
                            st.write(f"**작가:** {row['작가']}")
                            st.write(f"**줄거리 요약:** {row['요약']}")
                            st.write(f"**인상 깊은 내용:** {row['인상깊은 내용']}")
                            st.write(f"**질문:** {row['질문']}")
                            st.write(f"**답변:** {row['답변']}")
                            st.write(f"**느낀점:** {row['느낀점']}")

# -------------------------------------------------------------------
# 5. 교사용 화면
# -------------------------------------------------------------------
else:
    st.title("👩‍🏫 교사 관리 대시보드")
    teacher_pw = st.sidebar.text_input("교사 비밀번호 입력", type="password")
    
    if teacher_pw == "0923":
        st.success("교사 인증이 완료되었습니다.")
        
        tab_t1, tab_t2, tab_t3 = st.tabs(["📥 제출된 포트폴리오 조회", "📆 차시별 작성 날짜 관리", "👥 학생 명단 조회"])
        
        with tab_t1:
            st.markdown("### 📊 학생 제출 기록 보기")
            ws_logs = get_worksheet("reading_logs")
            df_logs = pd.DataFrame(ws_logs.get_all_records())
            
            if df_logs.empty:
                st.info("제출된 독서 기록이 없습니다.")
            else:
                st.dataframe(df_logs, use_container_width=True)
                
        with tab_t2:
            st.markdown("### 📆 반별 작성 허용 날짜 등록")
            ws_dates = get_worksheet("allowed_class_dates")
            df_dates = pd.DataFrame(ws_dates.get_all_records())
            st.dataframe(df_dates, use_container_width=True)

        with tab_t3:
            st.markdown("### 👥 등록된 학생 명단")
            ws_std = get_worksheet("student_list")
            df_std = pd.DataFrame(ws_std.get_all_records())
            st.dataframe(df_std, use_container_width=True)
