import streamlit as st
import pandas as pd
from datetime import datetime, date
import json

import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types


# ============================================================
# 1. 기본 설정
# ============================================================

SPREADSHEET_NAME = "중학교_독서포트폴리오_DB"

# AI 평가에 사용할 모델
GEMINI_MODEL = "gemini-2.5-flash"

# portfolio_scores 시트의 열 이름
SCORE_HEADERS = [
    "평가ID",
    "학년",
    "반",
    "번호",
    "이름",
    "AI_내용이해",
    "AI_작성충실도",
    "AI_감상의깊이",
    "작성횟수_자동",
    "AI_총점",
    "교사_내용이해",
    "교사_작성충실도",
    "교사_감상의깊이",
    "교사_작성횟수",
    "최종점수",
    "AI_평가근거",
    "AI_종합피드백",
    "교사_피드백",
    "평가일"
]


# ============================================================
# 2. Google Sheets 연결
# ============================================================

@st.cache_resource(show_spinner=False)
def get_gspread_client():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = dict(st.secrets["gcp_service_account"])

    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace(
            "\\n",
            "\n"
        )

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes
    )

    return gspread.authorize(credentials)


@st.cache_resource(show_spinner=False)
def get_spreadsheet():

    gc = get_gspread_client()

    return gc.open(SPREADSHEET_NAME)


def get_worksheet(sheet_name):

    sh = get_spreadsheet()

    return sh.worksheet(sheet_name)


@st.cache_data(ttl=30, show_spinner=False)
def read_sheet_records(sheet_name):
    """Google Sheets 읽기를 30초 동안 캐시하여 API 읽기 요청을 줄입니다."""
    ws = get_worksheet(sheet_name)
    return ws.get_all_records()


@st.cache_data(ttl=30, show_spinner=False)
def read_sheet_headers(sheet_name):
    """시트 1행 헤더 읽기를 30초 동안 캐시합니다."""
    ws = get_worksheet(sheet_name)
    return ws.row_values(1)


# ============================================================
# 3. Gemini 연결
# ============================================================

@st.cache_resource(show_spinner=False)
def get_gemini_client():
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception(
                "GEMINI_API_KEY를 Streamlit Secrets에서 찾지 못했습니다."
            )

        api_key = str(api_key).strip()

        if not api_key:
            raise Exception(
                "GEMINI_API_KEY가 비어 있습니다."
            )

        return genai.Client(api_key=api_key)

    except Exception as e:
        raise Exception(f"Gemini 설정 확인 필요: {e}")


# ============================================================
# 4. 기본 UI 설정
# ============================================================

st.set_page_config(
    page_title="중학교 독서 포트폴리오",
    page_icon="📚",
    layout="wide"
)

st.markdown(
    """
    <style>

    .main-title {
        font-size: 30px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .sub-title {
        color: #6b7280;
        font-size: 15px;
        margin-bottom: 20px;
    }

    .score-box {
        border: 1px solid #e5e7eb;
        border-radius: 15px;
        padding: 18px;
        background: white;
        margin-bottom: 12px;
    }

    .score-number {
        font-size: 30px;
        font-weight: 800;
    }

    .ai-box {
        border: 1px solid #ddd6fe;
        border-radius: 15px;
        padding: 18px;
        background: #faf8ff;
    }

    .student-record {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 12px;
        background: #ffffff;
    }

    div[data-baseweb="select"] {
        margin-top: 0px !important;
    }

    .stTextInput input,
    .stTextArea textarea {
        font-size: 16px !important;
        border-radius: 10px !important;
    }

    .stButton button {
        font-size: 16px !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 5. 공통 함수
# ============================================================

def safe_str(value):
    """빈칸/NaN을 안전하게 문자열로 변환"""
    if pd.isna(value):
        return ""
    return str(value)


def get_submission_score(count):
    """
    ④ 작성 횟수 점수

    15회 이상 : 25점
    12~14회  : 20점
    9~11회   : 15점
    8회 이하 : 10점
    """

    if count >= 15:
        return 25
    elif count >= 12:
        return 20
    elif count >= 9:
        return 15
    else:
        return 10


def get_submission_level(count):

    if count >= 15:
        return "매우 우수"
    elif count >= 12:
        return "우수"
    elif count >= 9:
        return "보통"
    else:
        return "노력 요함"


def make_evaluation_id(grade, class_name, student_id):
    """
    학생 1명당 포트폴리오 평가 1개를 관리하기 위한 ID
    """
    return f"{grade}_{class_name}_{student_id}"


def ensure_score_sheet():

    ws = get_worksheet("portfolio_scores")

    current_headers = [
        str(h).replace("\ufeff", "").strip()
        for h in read_sheet_headers("portfolio_scores")
    ]

    # 실제 portfolio_scores 시트에서는 띄어쓰기를 사용하고 있어도
    # 내부에서는 SCORE_HEADERS의 이름으로 통일해서 처리합니다.
    if not current_headers:
        ws.append_row(SCORE_HEADERS)
        return ws

    normalized_headers = normalize_header_names(current_headers)
    missing = [h for h in SCORE_HEADERS if h not in normalized_headers]

    if missing:
        st.warning(
            "⚠️ portfolio_scores 시트의 1행 제목을 확인해 주세요.\n\n"
            f"확인되지 않은 제목: {', '.join(missing)}"
        )

    return ws


def normalize_header_names(headers):
    """
    portfolio_scores의 실제 헤더 모양과 관계없이 내부 이름으로 통일합니다.
    예: AI내용이해 / AI_내용이해 / AI 내용이해 → AI_내용이해
    """

    # 비교할 때는 공백과 밑줄을 모두 제거합니다.
    # 그래서 시트에서 공백/밑줄을 어떻게 입력했든 인식할 수 있습니다.
    canonical = {
        "평가ID": "평가ID",
        "학년": "학년",
        "반": "반",
        "번호": "번호",
        "이름": "이름",
        "AI내용이해": "AI_내용이해",
        "AI작성충실도": "AI_작성충실도",
        "AI감상의깊이": "AI_감상의깊이",
        "작성횟수자동": "작성횟수_자동",
        "AI총점": "AI_총점",
        "교사내용이해": "교사_내용이해",
        "교사작성충실도": "교사_작성충실도",
        "교사감상의깊이": "교사_감상의깊이",
        "교사작성횟수": "교사_작성횟수",
        "최종점수": "최종점수",
        "AI평가근거": "AI_평가근거",
        "AI종합피드백": "AI_종합피드백",
        "교사피드백": "교사_피드백",
        "평가일": "평가일",
    }

    result = []
    for h in headers:
        text = str(h).replace("\ufeff", "").strip()
        compact = text.replace(" ", "").replace("_", "")
        result.append(canonical.get(compact, text))

    return result


def normalize_score_dataframe(df):
    """portfolio_scores 데이터를 내부 SCORE_HEADERS 구조로 맞춥니다."""

    if df is None or df.empty:
        return pd.DataFrame(columns=SCORE_HEADERS)

    df = df.copy()

    # 실제 시트의 띄어쓰기 헤더를 내부의 밑줄 헤더로 변환
    df.columns = normalize_header_names(df.columns)

    # 필수 열이 없더라도 빈 열을 만들어 KeyError 방지
    for col in SCORE_HEADERS:
        if col not in df.columns:
            df[col] = ""

    return df[SCORE_HEADERS].copy()


def find_existing_evaluation(ws, evaluation_id):

    records = read_sheet_records("portfolio_scores")

    if not records:
        return None, None

    df = normalize_score_dataframe(
        pd.DataFrame(records)
    )

    matches = df[
        df["평가ID"].astype(str).str.strip() == str(evaluation_id).strip()
    ]

    if matches.empty:
        return None, None

    row_index = matches.index[0] + 2

    return matches.iloc[0], row_index


# ============================================================
# 6. AI 평가 함수
# ============================================================

def run_ai_evaluation(student_name, book_records):

    client = get_gemini_client()

    # --------------------------------------------------------
    # 학생의 누적 기록을 AI가 읽을 수 있는 형태로 변환
    # --------------------------------------------------------

    records_text = ""

    for i, row in enumerate(book_records, start=1):

        records_text += f"""
========================
제출 기록 {i}
========================

날짜:
{safe_str(row.get("날짜"))}

책 제목:
{safe_str(row.get("책 제목"))}

작가:
{safe_str(row.get("작가"))}

읽은 페이지:
{safe_str(row.get("읽은 페이지"))}

요약:
{safe_str(row.get("요약"))}

인상 깊은 내용:
{safe_str(row.get("인상깊은 내용"))}

질문:
{safe_str(row.get("질문"))}

답변:
{safe_str(row.get("답변"))}

느낀점:
{safe_str(row.get("느낀점"))}

"""

    # --------------------------------------------------------
    # 루브릭
    # --------------------------------------------------------

    rubric = """
[1. 내용의 이해도 / 25점]

25점 - 매우 우수
글의 핵심 내용과 인물의 심리 및 사건의 인과관계를
정확하고 깊이 있게 이해하여 왜곡 없이 요약함.

20점 - 우수
글의 대체적인 흐름과 중요 사건을 바르게 파악하고
요약하였으나, 일부 세부 맥락의 서술이 다소 평이함.

15점 - 보통
글의 표면적인 줄거리는 파악하였으나,
핵심 주제나 인물 간의 관계 이해가 다소 피상적임.

10점 - 노력 요함
읽은 부분의 줄거리 요약이 누락되었거나
책의 전개 내용과 일치하지 않는 부분이 많음.


[2. 작성의 충실도 / 25점]

25점 - 매우 우수
요약, 인상 깊은 문장, 질문과 답변, 생각과 느낌 등
모든 항목을 분량 기준에 맞추어 성실하고 구체적으로 작성함.

20점 - 우수
모든 필수 항목을 빠짐없이 작성하였으나,
일부 항목의 서술 분량이 다소 간략함.

15점 - 보통
필수 항목 중 1~2개 항목의 내용이 형식적으로 작성되었거나
글자 수가 부족함.

10점 - 노력 요함
항목의 미작성이 있거나 단답형으로 작성되어
성실도가 현저히 부족함.


[3. 감상의 깊이 / 25점]

25점 - 매우 우수
작품의 내용을 자신의 삶, 학교생활, 사회적 이슈와
창의적·비판적으로 연결하여 성찰적 생각을 심도 있게 서술함.

20점 - 우수
자신의 솔직한 느낌과 생각을 진솔하게 드러내었으나,
일반적인 교훈 수준에 머물러 독창성이 약간 아쉬움.

15점 - 보통
단순한 재미나 단편적 인상 위주로 감상을 기술하여
성찰이 부족함.

10점 - 노력 요함
감상과 느낌이 한 줄 이하이거나
줄거리의 단순 반복으로 구성되어 독창적 감상을 찾기 어려움.
"""

    # --------------------------------------------------------
    # Gemini에게 줄 지시
    # --------------------------------------------------------

    system_prompt = f"""
너는 중학교 국어 교사의 독서 포트폴리오 수행평가를
보조하는 평가 AI이다.

학생의 전체 누적 독서 기록을 바탕으로 교사의 루브릭에 따라
평가 점수를 '추천'한다.

중요한 원칙:

1. 학생의 실제 작성 내용에 근거해서만 판단한다.
2. 기록에 없는 내용을 추측하지 않는다.
3. 학생의 글쓰기 능력 자체보다 제시된 루브릭의 기준을 적용한다.
4. 점수는 반드시 10, 15, 20, 25 중 하나만 사용한다.
5. 4번 '작성 횟수'는 AI가 평가하지 않는다.
6. 4번 작성 횟수는 프로그램이 실제 제출 횟수로 계산한다.
7. AI의 평가는 최종 성적이 아니라 교사가 검토할 수 있는
   '추천 평가'이다.
8. 평가 근거는 학생이 실제로 작성한 내용에 근거하여 구체적으로 작성한다.
9. 근거 없는 칭찬이나 비판은 하지 않는다.

{rubric}
"""

    user_prompt = f"""
학생 이름: {student_name}

이 학생의 누적 독서 포트폴리오 기록은 다음과 같다.

{records_text}

위 자료를 바탕으로 1~3번 영역을 평가하라.

각 영역은 반드시 10, 15, 20, 25 중 하나의 점수를 선택하라.

종합피드백은 학생에게 직접 말하는 것이 아니라
교사가 평가 결과를 참고할 수 있는 형태로 작성한다.
"""

    # Gemini 구조화 출력용 JSON Schema
    # Google 공식 Gemini API는 response_mime_type과
    # response_schema를 사용해 JSON 형식 출력을 지원합니다.
    schema = {
        "type": "OBJECT",
        "properties": {
            "내용이해_점수": {
                "type": "INTEGER",
                "enum": [10, 15, 20, 25]
            },
            "작성충실도_점수": {
                "type": "INTEGER",
                "enum": [10, 15, 20, 25]
            },
            "감상의깊이_점수": {
                "type": "INTEGER",
                "enum": [10, 15, 20, 25]
            },
            "내용이해_근거": {
                "type": "STRING"
            },
            "작성충실도_근거": {
                "type": "STRING"
            },
            "감상의깊이_근거": {
                "type": "STRING"
            },
            "종합피드백": {
                "type": "STRING"
            }
        },
        "required": [
            "내용이해_점수",
            "작성충실도_점수",
            "감상의깊이_점수",
            "내용이해_근거",
            "작성충실도_근거",
            "감상의깊이_근거",
            "종합피드백"
        ],
        "additionalProperties": False
    }

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            system_prompt,
            user_prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2
        )
    )

    if not response.text:
        raise Exception(
            "Gemini가 빈 응답을 반환했습니다."
        )

    result = json.loads(response.text)

    # 구조화 출력이더라도 애플리케이션에서 한 번 더 검증
    allowed_scores = {10, 15, 20, 25}

    for key in [
        "내용이해_점수",
        "작성충실도_점수",
        "감상의깊이_점수"
    ]:
        if int(result[key]) not in allowed_scores:
            raise Exception(
                f"Gemini 평가 점수가 올바르지 않습니다: {result[key]}"
            )
        result[key] = int(result[key])

    return result


# ============================================================
# 7. 평가 결과 저장
# ============================================================

def save_evaluation(
    ws,
    evaluation_id,
    grade,
    class_name,
    student_id,
    student_name,
    ai_understanding,
    ai_completeness,
    ai_depth,
    submission_count,
    ai_total,
    teacher_understanding,
    teacher_completeness,
    teacher_depth,
    teacher_count,
    final_score,
    ai_reason,
    ai_feedback,
    teacher_feedback
):

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    row_values = [
        evaluation_id,
        grade,
        class_name,
        student_id,
        student_name,
        ai_understanding,
        ai_completeness,
        ai_depth,
        submission_count,
        ai_total,
        teacher_understanding,
        teacher_completeness,
        teacher_depth,
        teacher_count,
        final_score,
        ai_reason,
        ai_feedback,
        teacher_feedback,
        now
    ]

    existing, row_index = find_existing_evaluation(
        ws,
        evaluation_id
    )

    if row_index is None:

        ws.append_row(
            row_values,
            value_input_option="USER_ENTERED"
        )

    else:

        ws.update(
            f"A{row_index}:S{row_index}",
            [row_values],
            value_input_option="USER_ENTERED"
        )


# ============================================================
# 8. 사이드바
# ============================================================

st.sidebar.header("🔐 접속 모드")

user_type = st.sidebar.radio(
    "모드를 선택하세요",
    [
        "👨‍🎓 학생용 (독서 기록)",
        "👩‍🏫 교사용 (관리 및 피드백)"
    ]
)


# ============================================================
# 9. 학생용 화면
# ============================================================

if user_type == "👨‍🎓 학생용 (독서 기록)":

    st.markdown(
        '<div class="main-title">📚 나의 독서 포트폴리오</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">독서 기록을 차곡차곡 쌓아 보세요.</div>',
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # 학생 로그인
    # --------------------------------------------------------

    if "logged_in_student" not in st.session_state:

        with st.form("student_login_form"):

            st.markdown("### 🔑 학생 로그인")

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                grade = st.selectbox(
                    "학년",
                    ["1학년", "2학년", "3학년"],
                    key="s_grade"
                )

            with c2:
                class_name = st.selectbox(
                    "반",
                    [
                        "1반",
                        "2반",
                        "3반",
                        "4반",
                        "5반",
                        "6반",
                        "7반",
                        "8반"
                    ],
                    key="s_class"
                )

            with c3:
                student_id = st.text_input(
                    "번호",
                    key="s_id"
                )

            with c4:
                pin = st.text_input(
                    "고유번호 (PIN 4자리)",
                    type="password",
                    key="s_pin"
                )

            login_btn = st.form_submit_button(
                "🚀 학생 포트폴리오 입장하기",
                use_container_width=True
            )

        if login_btn:

            if not student_id or not pin:

                st.warning(
                    "⚠️ 번호와 고유번호를 모두 입력해 주세요."
                )

            else:

                try:

                    ws_std = get_worksheet(
                        "student_list"
                    )

                    df_std = pd.DataFrame(
                        read_sheet_records("student_list")
                    )

                    user_match = df_std[
                        (df_std["학년"].astype(str) == str(grade)) &
                        (df_std["반"].astype(str) == str(class_name)) &
                        (df_std["번호"].astype(str) == str(student_id)) &
                        (df_std["고유번호"].astype(str) == str(pin))
                    ]

                    if user_match.empty:

                        st.error(
                            "❌ 학년, 반, 번호 또는 고유번호가 일치하지 않습니다."
                        )

                    else:

                        st.session_state[
                            "logged_in_student"
                        ] = {
                            "grade": grade,
                            "class_name": class_name,
                            "student_id": student_id,
                            "student_name": user_match.iloc[0]["이름"]
                        }

                        st.rerun()

                except Exception as e:

                    st.error(
                        f"구글 시트 연결 오류: {e}"
                    )

    # --------------------------------------------------------
    # 로그인 성공
    # --------------------------------------------------------

    else:

        std_info = st.session_state[
            "logged_in_student"
        ]

        s_grade = std_info["grade"]
        s_class = std_info["class_name"]
        s_id = std_info["student_id"]
        s_name = std_info["student_name"]

        c_top1, c_top2 = st.columns(
            [4, 1]
        )

        with c_top1:

            st.success(
                f"👋 [{s_grade} {s_class} {s_id}번] "
                f"{s_name} 학생 환영합니다!"
            )

        with c_top2:

            if st.button(
                "로그아웃",
                use_container_width=True
            ):

                del st.session_state[
                    "logged_in_student"
                ]

                st.rerun()

        today_str = date.today().strftime(
            "%Y-%m-%d"
        )

        # ----------------------------------------------------
        # 작성 가능 날짜 확인
        # ----------------------------------------------------

        try:

            ws_dates = get_worksheet(
                "allowed_class_dates"
            )

            df_dates = pd.DataFrame(
                read_sheet_records("allowed_class_dates")
            )

            grade_col = (
                "학년"
                if "학년" in df_dates.columns
                else "grade"
            )

            class_col = (
                "반"
                if "반" in df_dates.columns
                else "class_name"
            )

            date_col = (
                "날짜"
                if "날짜" in df_dates.columns
                else "allowed_date"
            )

            session_col = (
                "차시"
                if "차시" in df_dates.columns
                else "session_num"
            )

            date_record = df_dates[
                (df_dates[grade_col].astype(str) == str(s_grade)) &
                (df_dates[class_col].astype(str) == str(s_class)) &
                (df_dates[date_col].astype(str) == str(today_str))
            ]

        except Exception:

            date_record = pd.DataFrame()

        tab1, tab2 = st.tabs(
            [
                "📝 오늘의 독서 기록 쓰기",
                "📖 내 과거 기록 보기"
            ]
        )

        # ----------------------------------------------------
        # 오늘 기록
        # ----------------------------------------------------

        with tab1:

            if date_record.empty:

                st.error(
                    f"⛔ [{s_grade} {s_class}]은(는) "
                    f"오늘({today_str}) 독서 기록 작성 허용 날짜가 아닙니다."
                )

            else:

                session_name = date_record.iloc[0][
                    session_col
                ]

                st.info(
                    f"📌 현재 진행 차시: "
                    f"{s_grade} {s_class} - {session_name}"
                )

                with st.form("reading_form"):

                    col_b1, col_b2 = st.columns(2)

                    with col_b1:

                        book_title = st.text_input(
                            "책 제목 *"
                        )

                        author = st.text_input(
                            "작가 이름 *"
                        )

                    with col_b2:

                        pages_read = st.text_input(
                            "오늘 읽은 페이지 범위 "
                            "(예: 12~35p) *"
                        )

                    summary = st.text_area(
                        "1. 오늘 읽은 내용 짧은 요약 "
                        "(핵심 줄거리) *",
                        height=110
                    )

                    quote = st.text_area(
                        "2. 가장 인상 깊은 문장과 이유",
                        height=90
                    )

                    st.markdown(
                        "##### 3. 읽은 내용을 바탕으로 만든 질문과 답변"
                    )

                    col_q1, col_q2 = st.columns(2)

                    with col_q1:

                        question_text = st.text_area(
                            "3-1. 나의 질문",
                            height=100,
                            placeholder="예: 주인공은 왜 그런 선택을 했을까?"
                        )

                    with col_q2:

                        answer_text = st.text_area(
                            "3-2. 질문에 대한 나의 생각/답변",
                            height=100,
                            placeholder="예: 자신의 가치관을 지키기 위해서였을 것이다."
                        )

                    reflection = st.text_area(
                        "4. 나의 생각과 느낌 "
                        "(느낀점/깨달은점) *",
                        height=130
                    )

                    submit_btn = st.form_submit_button(
                        "🚀 독서 기록 제출하기",
                        use_container_width=True
                    )

                    if submit_btn:

                        if (
                            not book_title
                            or not pages_read
                            or not summary
                            or not reflection
                        ):

                            st.error(
                                "필수 항목(*)을 빠짐없이 입력해 주세요!"
                            )

                        else:

                            ws_logs = get_worksheet(
                                "reading_logs"
                            )

                            ws_logs.append_row(
                                [
                                    str(s_grade),
                                    str(s_class),
                                    str(s_id),
                                    str(s_name),
                                    book_title,
                                    author,
                                    today_str,
                                    pages_read,
                                    summary,
                                    quote,
                                    question_text,
                                    answer_text,
                                    reflection,
                                    datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                ]
                            )

                            st.cache_data.clear()

                            st.balloons()

                            st.success(
                                "오늘의 독서 기록이 "
                                "구글 시트에 안전하게 제출되었습니다!"
                            )

        # ----------------------------------------------------
        # 과거 기록
        # ----------------------------------------------------

        with tab2:

            try:

                ws_logs = get_worksheet(
                    "reading_logs"
                )

                df_logs = pd.DataFrame(
                    read_sheet_records("reading_logs")
                )

                if not df_logs.empty:

                    my_logs = df_logs[
                        (df_logs["학년"].astype(str) == str(s_grade)) &
                        (df_logs["반"].astype(str) == str(s_class)) &
                        (df_logs["번호"].astype(str) == str(s_id))
                    ]

                    if my_logs.empty:

                        st.info(
                            "아직 제출된 기록이 없습니다."
                        )

                    else:

                        for _, row in my_logs.iterrows():

                            with st.expander(
                                f"📌 [{row['날짜']}] "
                                f"{row['책 제목']} "
                                f"({row['읽은 페이지']})"
                            ):

                                st.write(
                                    f"**작가:** {row['작가']}"
                                )

                                st.write(
                                    f"**줄거리 요약:** {row['요약']}"
                                )

                                st.write(
                                    f"**인상 깊은 내용:** "
                                    f"{row['인상깊은 내용']}"
                                )

                                st.write(
                                    f"**질문:** {row['질문']}"
                                )

                                st.write(
                                    f"**답변:** {row['답변']}"
                                )

                                st.write(
                                    f"**느낀점:** {row['느낀점']}"
                                )

            except Exception as e:

                st.error(
                    f"기록 조회 오류: {e}"
                )


# ============================================================
# 10. 교사용 화면
# ============================================================

else:

    st.markdown(
        '<div class="main-title">👩‍🏫 독서 포트폴리오 교사 관리 대시보드</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        '학생의 누적 독서 기록을 확인하고 AI 평가를 검토·수정할 수 있습니다.'
        '</div>',
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # 교사 비밀번호
    # --------------------------------------------------------

    teacher_pw = st.sidebar.text_input(
        "교사 비밀번호 입력",
        type="password"
    )

    if teacher_pw != "0923":

        st.info(
            "🔐 교사용 화면을 이용하려면 "
            "교사 비밀번호를 입력해 주세요."
        )

        st.stop()

    st.success(
        "교사 인증이 완료되었습니다."
    )

    # --------------------------------------------------------
    # 데이터 불러오기
    # --------------------------------------------------------

    try:

        ws_logs = get_worksheet(
            "reading_logs"
        )

        df_logs = pd.DataFrame(
            read_sheet_records("reading_logs")
        )

        ws_std = get_worksheet(
            "student_list"
        )

        df_std = pd.DataFrame(
            read_sheet_records("student_list")
        )

        ws_scores = ensure_score_sheet()

        score_records = read_sheet_records("portfolio_scores")

        if score_records:

            df_scores = pd.DataFrame(
                score_records
            )

        else:

            df_scores = pd.DataFrame(
                columns=SCORE_HEADERS
            )

        # portfolio_scores의 실제 열 구조가 조금 달라도
        # 항상 SCORE_HEADERS에 맞춰서 사용합니다.
        df_scores = normalize_score_dataframe(
            df_scores
        )

    except Exception as e:

        st.error(
            f"구글 시트 읽기 오류: {e}"
        )

        st.stop()

    # --------------------------------------------------------
    # 상단 통계
    # --------------------------------------------------------

    total_students = len(df_std)

    if not df_logs.empty:

        submitted_students = df_logs[
            ["학년", "반", "번호"]
        ].drop_duplicates().shape[0]

        total_records = len(df_logs)

    else:

        submitted_students = 0
        total_records = 0

    if not df_scores.empty:

        completed_evaluations = len(
            df_scores[
                df_scores["최종점수"].astype(str).str.strip() != ""
            ]
        )

    else:

        completed_evaluations = 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "등록 학생",
            f"{total_students}명"
        )

    with col2:

        st.metric(
            "제출 학생",
            f"{submitted_students}명"
        )

    with col3:

        st.metric(
            "전체 독서 기록",
            f"{total_records}회"
        )

    with col4:

        st.metric(
            "평가 완료",
            f"{completed_evaluations}명"
        )

    st.divider()

    # ========================================================
    # 필터
    # ========================================================

    st.markdown(
        "### 🔎 학생 필터"
    )

    f1, f2, f3 = st.columns(
        [1, 1, 2]
    )

    # --------------------------------------------------------
    # 학년
    # --------------------------------------------------------

    with f1:

        if not df_std.empty:

            grades = sorted(
                df_std["학년"].astype(str).unique().tolist()
            )

        else:

            grades = []

        grade_options = ["전체"] + grades

        selected_grade = st.selectbox(
            "학년",
            grade_options
        )

    # --------------------------------------------------------
    # 반
    # --------------------------------------------------------

    with f2:

        temp_std = df_std.copy()

        if (
            selected_grade != "전체"
            and not temp_std.empty
        ):

            temp_std = temp_std[
                temp_std["학년"].astype(str)
                == str(selected_grade)
            ]

        if not temp_std.empty:

            classes = sorted(
                temp_std["반"].astype(str).unique().tolist()
            )

        else:

            classes = []

        class_options = ["전체"] + classes

        selected_class = st.selectbox(
            "반",
            class_options
        )

    # --------------------------------------------------------
    # 학생
    # --------------------------------------------------------

    with f3:

        temp_students = df_std.copy()

        if selected_grade != "전체":

            temp_students = temp_students[
                temp_students["학년"].astype(str)
                == str(selected_grade)
            ]

        if selected_class != "전체":

            temp_students = temp_students[
                temp_students["반"].astype(str)
                == str(selected_class)
            ]

        student_options = ["전체"]

        student_map = {}

        if not temp_students.empty:

            for _, row in temp_students.iterrows():

                student_label = (
                    f"{row['번호']}번 "
                    f"{row['이름']}"
                )

                student_options.append(
                    student_label
                )

                student_map[
                    student_label
                ] = row

        saved_selected_student = st.session_state.get(
            "selected_student_label",
            "전체"
        )

        if saved_selected_student not in student_options:
            saved_selected_student = "전체"

        # 버튼으로 학생을 선택한 경우 selectbox의 값도 함께 변경
        st.session_state["teacher_student_select"] = saved_selected_student

        selected_student = st.selectbox(
            "학생",
            student_options,
            key="teacher_student_select"
        )

        # 드롭다운에서 학생을 직접 선택한 경우에도 상태를 유지
        st.session_state["selected_student_label"] = selected_student

    # ========================================================
    # 학생 목록
    # ========================================================

    if selected_student == "전체":

        st.markdown(
            "### 👥 학생 목록"
        )

        if temp_students.empty:

            st.info(
                "조건에 해당하는 학생이 없습니다."
            )

        else:

            display_rows = []

            for _, student in temp_students.iterrows():

                grade = safe_str(
                    student["학년"]
                )

                class_name = safe_str(
                    student["반"]
                )

                student_id = safe_str(
                    student["번호"]
                )

                student_name = safe_str(
                    student["이름"]
                )

                if not df_logs.empty:

                    student_logs = df_logs[
                        (df_logs["학년"].astype(str) == grade) &
                        (df_logs["반"].astype(str) == class_name) &
                        (df_logs["번호"].astype(str) == student_id)
                    ]

                    count = len(student_logs)

                else:

                    count = 0

                evaluation_id = make_evaluation_id(
                    grade,
                    class_name,
                    student_id
                )

                final_score = ""

                if not df_scores.empty:

                    score_match = df_scores[
                        df_scores["평가ID"].astype(str)
                        == evaluation_id
                    ]

                    if not score_match.empty:

                        final_score = safe_str(
                            score_match.iloc[0]["최종점수"]
                        )

                if final_score:

                    status = "✅ 평가완료"

                elif count > 0:

                    status = "🟡 평가대기"

                else:

                    status = "⚪ 미제출"

                display_rows.append(
                    {
                        "번호": student_id,
                        "이름": student_name,
                        "학년": grade,
                        "반": class_name,
                        "작성 횟수": count,
                        "작성 점수": get_submission_score(count),
                        "최종 점수": final_score,
                        "상태": status
                    }
                )

            display_df = pd.DataFrame(
                display_rows
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            st.info(
                "👆 위 표의 행을 직접 클릭하는 기능은 Streamlit의 data_editor가 아니면 선택값으로 연결되지 않습니다. "
                "아래에서 학생 이름 옆의 [학생 보기] 버튼을 누르거나, 위의 학생 선택 메뉴에서 학생을 선택하세요."
            )

            # 표의 학생을 실제로 선택할 수 있도록 버튼 제공
            for _, student_row in temp_students.iterrows():
                _grade = safe_str(student_row["학년"])
                _class = safe_str(student_row["반"])
                _num = safe_str(student_row["번호"])
                _name = safe_str(student_row["이름"])
                _label = f"{_num}번 {_name}"

                _c1, _c2 = st.columns([5, 1])
                with _c1:
                    st.write(f"**{_label}**  ·  {_grade}학년 {_class}반")
                with _c2:
                    if st.button(
                        "학생 보기",
                        key=f"view_student_{_grade}_{_class}_{_num}",
                        use_container_width=True
                    ):
                        st.session_state["selected_student_label"] = _label
                        st.rerun()

            st.stop()

    # ========================================================
    # 선택 학생 정보
    # ========================================================

    student = student_map[
        selected_student
    ]

    grade = safe_str(
        student["학년"]
    )

    class_name = safe_str(
        student["반"]
    )

    student_id = safe_str(
        student["번호"]
    )

    student_name = safe_str(
        student["이름"]
    )

    evaluation_id = make_evaluation_id(
        grade,
        class_name,
        student_id
    )

    # --------------------------------------------------------
    # 학생 독서 기록
    # --------------------------------------------------------

    if not df_logs.empty:

        student_logs = df_logs[
            (df_logs["학년"].astype(str) == grade) &
            (df_logs["반"].astype(str) == class_name) &
            (df_logs["번호"].astype(str) == student_id)
        ].copy()

    else:

        student_logs = pd.DataFrame()

    submission_count = len(
        student_logs
    )

    automatic_count_score = get_submission_score(
        submission_count
    )

    count_level = get_submission_level(
        submission_count
    )

    # --------------------------------------------------------
    # 기존 평가 가져오기
    # --------------------------------------------------------

    existing_evaluation, existing_row_index = find_existing_evaluation(
        ws_scores,
        evaluation_id
    )

    # ========================================================
    # 학생 헤더
    # ========================================================

    st.divider()

    header_left, header_right = st.columns(
        [4, 1]
    )

    with header_left:

        st.markdown(
            f"## 👤 {student_name} "
            f"<span style='font-size:16px;color:#6b7280;'>"
            f"({grade} {class_name} {student_id}번)"
            f"</span>",
            unsafe_allow_html=True
        )

        st.caption(
            f"누적 독서 기록 {submission_count}회"
        )

    with header_right:

        if submission_count >= 15:

            st.success(
                f"작성 횟수 {submission_count}회"
            )

        elif submission_count >= 9:

            st.warning(
                f"작성 횟수 {submission_count}회"
            )

        else:

            st.error(
                f"작성 횟수 {submission_count}회"
            )

    # ========================================================
    # 왼쪽: 학생 기록 / 오른쪽: 평가
    # ========================================================

    left_col, right_col = st.columns(
        [1.25, 1],
        gap="large"
    )

    # ========================================================
    # 왼쪽 학생 기록
    # ========================================================

    with left_col:

        st.markdown(
            "### 📚 제출된 독서 포트폴리오"
        )

        if student_logs.empty:

            st.warning(
                "아직 제출된 독서 기록이 없습니다."
            )

        else:

            # 날짜순 정렬
            if "날짜" in student_logs.columns:

                student_logs = student_logs.sort_values(
                    by="날짜"
                )

            for i, (_, row) in enumerate(
                student_logs.iterrows(),
                start=1
            ):

                book_title = safe_str(
                    row.get("책 제목")
                )

                log_date = safe_str(
                    row.get("날짜")
                )

                with st.expander(
                    f"📖 {i}차시 · "
                    f"{log_date} · "
                    f"{book_title}",
                    expanded=(i == len(student_logs))
                ):

                    st.markdown(
                        f"**작가:** "
                        f"{safe_str(row.get('작가'))}"
                    )

                    st.markdown(
                        f"**읽은 페이지:** "
                        f"{safe_str(row.get('읽은 페이지'))}"
                    )

                    st.markdown(
                        "#### ① 오늘 읽은 내용 요약"
                    )

                    st.write(
                        safe_str(row.get("요약"))
                    )

                    st.markdown(
                        "#### ② 인상 깊은 내용"
                    )

                    st.write(
                        safe_str(row.get("인상깊은 내용"))
                    )

                    st.markdown(
                        "#### ③ 나의 질문"
                    )

                    st.write(
                        safe_str(row.get("질문"))
                    )

                    st.markdown(
                        "#### ④ 질문에 대한 답변"
                    )

                    st.write(
                        safe_str(row.get("답변"))
                    )

                    st.markdown(
                        "#### ⑤ 나의 생각과 느낌"
                    )

                    st.write(
                        safe_str(row.get("느낀점"))
                    )

    # ========================================================
    # 오른쪽: 평가
    # ========================================================

    with right_col:

        st.markdown(
            "### 🤖 AI 수행평가"
        )

        st.info(
            "AI는 ① 내용의 이해도, "
            "② 작성의 충실도, "
            "③ 감상의 깊이를 평가합니다. "
            "④ 작성 횟수는 실제 제출 횟수로 자동 계산됩니다."
        )

        # ----------------------------------------------------
        # 기존 AI 평가값
        # ----------------------------------------------------

        ai_understanding = 0
        ai_completeness = 0
        ai_depth = 0
        ai_total = 0
        ai_reason = ""
        ai_feedback = ""

        teacher_understanding = 10
        teacher_completeness = 10
        teacher_depth = 10
        teacher_count = automatic_count_score
        teacher_feedback = ""

        if existing_evaluation is not None:

            try:

                ai_understanding = int(
                    float(
                        safe_str(
                            existing_evaluation["AI_내용이해"]
                        ) or 0
                    )
                )

                ai_completeness = int(
                    float(
                        safe_str(
                            existing_evaluation["AI_작성충실도"]
                        ) or 0
                    )
                )

                ai_depth = int(
                    float(
                        safe_str(
                            existing_evaluation["AI_감상의깊이"]
                        ) or 0
                    )
                )

                ai_total = int(
                    float(
                        safe_str(
                            existing_evaluation["AI_총점"]
                        ) or 0
                    )
                )

                ai_reason = safe_str(
                    existing_evaluation["AI_평가근거"]
                )

                ai_feedback = safe_str(
                    existing_evaluation["AI_종합피드백"]
                )

                teacher_understanding = int(
                    float(
                        safe_str(
                            existing_evaluation["교사_내용이해"]
                        )
                        or ai_understanding
                        or 10
                    )
                )

                teacher_completeness = int(
                    float(
                        safe_str(
                            existing_evaluation["교사_작성충실도"]
                        )
                        or ai_completeness
                        or 10
                    )
                )

                teacher_depth = int(
                    float(
                        safe_str(
                            existing_evaluation["교사_감상의깊이"]
                        )
                        or ai_depth
                        or 10
                    )
                )

                teacher_count = automatic_count_score

                saved_teacher_feedback = safe_str(
                    existing_evaluation["교사_피드백"]
                )

                teacher_feedback = (
                    saved_teacher_feedback
                )

            except Exception:

                pass

        # ----------------------------------------------------
        # AI 실행 버튼
        # ----------------------------------------------------

        if st.button(
            "✨ AI 자동 채점 실행",
            use_container_width=True,
            type="primary"
        ):

            if student_logs.empty:

                st.error(
                    "학생의 독서 기록이 없습니다."
                )

            else:

                records = (
                    student_logs
                    .fillna("")
                    .to_dict("records")
                )

                with st.spinner(
                    "AI가 학생의 누적 독서 포트폴리오를 분석하고 있습니다..."
                ):

                    try:

                        ai_result = run_ai_evaluation(
                            student_name,
                            records
                        )

                        ai_understanding = int(
                            ai_result[
                                "내용이해_점수"
                            ]
                        )

                        ai_completeness = int(
                            ai_result[
                                "작성충실도_점수"
                            ]
                        )

                        ai_depth = int(
                            ai_result[
                                "감상의깊이_점수"
                            ]
                        )

                        ai_total = (
                            ai_understanding
                            + ai_completeness
                            + ai_depth
                            + automatic_count_score
                        )

                        ai_reason = (
                            "① 내용의 이해도\n"
                            + ai_result[
                                "내용이해_근거"
                            ]
                            + "\n\n"
                            + "② 작성의 충실도\n"
                            + ai_result[
                                "작성충실도_근거"
                            ]
                            + "\n\n"
                            + "③ 감상의 깊이\n"
                            + ai_result[
                                "감상의깊이_근거"
                            ]
                        )

                        ai_feedback = ai_result[
                            "종합피드백"
                        ]

                        # AI 결과를 session_state에 저장
                        st.session_state[
                            f"ai_{evaluation_id}"
                        ] = {
                            "understanding": ai_understanding,
                            "completeness": ai_completeness,
                            "depth": ai_depth,
                            "total": ai_total,
                            "reason": ai_reason,
                            "feedback": ai_feedback
                        }

                        st.success(
                            "AI 평가가 완료되었습니다."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"AI 평가 중 오류가 발생했습니다: {e}"
                        )

        # ----------------------------------------------------
        # Session State의 최신 AI 결과 반영
        # ----------------------------------------------------

        session_ai_key = (
            f"ai_{evaluation_id}"
        )

        if session_ai_key in st.session_state:

            current_ai = st.session_state[
                session_ai_key
            ]

            ai_understanding = current_ai[
                "understanding"
            ]

            ai_completeness = current_ai[
                "completeness"
            ]

            ai_depth = current_ai[
                "depth"
            ]

            ai_total = current_ai[
                "total"
            ]

            ai_reason = current_ai[
                "reason"
            ]

            ai_feedback = current_ai[
                "feedback"
            ]

        # ----------------------------------------------------
        # AI 점수 표시
        # ----------------------------------------------------

        if ai_total > 0:

            st.markdown(
                f"""
                <div class="ai-box">
                    <div style="color:#6b7280;font-size:14px;">
                        AI 추천 총점
                    </div>
                    <div class="score-number">
                        {ai_total}
                        <span style="font-size:16px;">
                        / 100점
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.write("")

            a1, a2 = st.columns(2)

            with a1:

                st.metric(
                    "① 내용의 이해도",
                    f"{ai_understanding} / 25"
                )

                st.metric(
                    "② 작성의 충실도",
                    f"{ai_completeness} / 25"
                )

            with a2:

                st.metric(
                    "③ 감상의 깊이",
                    f"{ai_depth} / 25"
                )

                st.metric(
                    "④ 작성 횟수",
                    f"{automatic_count_score} / 25"
                )

            with st.expander(
                "🔍 AI 평가 근거 보기",
                expanded=False
            ):

                st.write(
                    ai_reason
                )

            with st.expander(
                "💬 AI 종합 피드백",
                expanded=True
            ):

                st.write(
                    ai_feedback
                )

        else:

            st.warning(
                "아직 AI 평가가 실행되지 않았습니다."
            )

        st.divider()

        # ====================================================
        # 교사 최종 평가
        # ====================================================

        st.markdown(
            "### ✏️ 교사 최종 평가"
        )

        st.caption(
            "AI 추천 점수를 검토한 뒤 선생님이 최종 점수를 직접 수정할 수 있습니다."
        )

        score_options = [
            25,
            20,
            15,
            10
        ]

        # ----------------------------------------------------
        # 교사 점수 - 버튼 선택 방식
        # ----------------------------------------------------

        def score_button_selector(label, current_value, state_key):
            """10/15/20/25점 중 하나를 버튼으로 선택합니다."""

            if state_key not in st.session_state:
                st.session_state[state_key] = (
                    current_value
                    if current_value in score_options
                    else 10
                )

            st.markdown(f"**{label}**")

            button_cols = st.columns(4)

            for col, score in zip(button_cols, score_options):
                with col:
                    is_selected = (
                        st.session_state[state_key] == score
                    )

                    if st.button(
                        f"{'✓ ' if is_selected else ''}{score}점",
                        key=f"{state_key}_{score}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary"
                    ):
                        st.session_state[state_key] = score

            selected_score = st.session_state[state_key]

            st.caption(
                f"현재 선택: **{selected_score}점 / 25점**"
            )

            return selected_score

        teacher_understanding = score_button_selector(
            "① 내용의 이해도",
            teacher_understanding,
            f"teacher_understanding_{evaluation_id}"
        )

        teacher_completeness = score_button_selector(
            "② 작성의 충실도",
            teacher_completeness,
            f"teacher_completeness_{evaluation_id}"
        )

        teacher_depth = score_button_selector(
            "③ 감상의 깊이",
            teacher_depth,
            f"teacher_depth_{evaluation_id}"
        )

        # ----------------------------------------------------
        # 작성 횟수는 자동 점수
        # ----------------------------------------------------

        st.markdown(
            f"""
            **④ 작성 횟수(누락 여부)**

            제출 횟수: **{submission_count}회**

            평가 수준: **{count_level}**

            자동 점수: **{automatic_count_score} / 25점**
            """
        )

        teacher_count = automatic_count_score

        # ----------------------------------------------------
        # 최종 점수
        # ----------------------------------------------------

        final_score = (
            teacher_understanding
            + teacher_completeness
            + teacher_depth
            + teacher_count
        )

        st.markdown(
            f"""
            <div class="score-box">
                <div style="color:#6b7280;">
                    교사 최종 평가 점수
                </div>
                <div class="score-number">
                    {final_score}
                    <span style="font-size:16px;">
                    / 100점
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # ----------------------------------------------------
        # 교사 피드백
        # ----------------------------------------------------

        teacher_feedback = st.text_area(
            "📝 교사 피드백",
            value=teacher_feedback,
            height=160,
            placeholder=(
                "학생에게 전달할 피드백이나 "
                "교사의 평가 메모를 입력하세요."
            ),
            key=f"teacher_feedback_{evaluation_id}"
        )

        # ----------------------------------------------------
        # 최종 평가 저장
        # ----------------------------------------------------

        if st.button(
            "💾 최종 평가 결과 저장",
            use_container_width=True,
            type="primary"
        ):

            try:

                # AI 결과가 아직 없는 경우
                # AI 점수는 빈 값으로 저장
                save_evaluation(
                    ws_scores,
                    evaluation_id,
                    grade,
                    class_name,
                    student_id,
                    student_name,
                    ai_understanding,
                    ai_completeness,
                    ai_depth,
                    submission_count,
                    ai_total,
                    teacher_understanding,
                    teacher_completeness,
                    teacher_depth,
                    teacher_count,
                    final_score,
                    ai_reason,
                    ai_feedback,
                    teacher_feedback
                )

                st.cache_data.clear()

                st.success(
                    f"✅ {student_name} 학생의 "
                    f"최종 평가가 저장되었습니다."
                )

                # 새로고침
                st.rerun()

            except Exception as e:

                st.error(
                    f"평가 결과 저장 중 오류가 발생했습니다: {e}"
                )

        # ----------------------------------------------------
        # 저장된 평가 정보
        # ----------------------------------------------------

        if existing_evaluation is not None:

            st.caption(
                "☑️ 이 학생은 이전에 평가 결과가 저장되어 있습니다."
            )
