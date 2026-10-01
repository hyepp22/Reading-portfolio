import streamlit as st
import pandas as pd
from datetime import datetime, date
import json
import time

import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

# ============================================================
# 학생 입력창 붙여넣기 차단
# ============================================================

def disable_paste():
    st.markdown(
        """
        <script>
        // Ctrl + V / Ctrl + Shift + V / Shift + Insert 차단
        document.addEventListener(
            "keydown",
            function(event) {
                if (
                    (event.ctrlKey &&
                    (event.key === "v" ||
                     event.key === "V")) ||
                    (event.shiftKey &&
                    event.key === "Insert")
                ) {
                    event.preventDefault();
                    alert(
                        "📢 붙여넣기는 사용할 수 없습니다.\\n직접 입력해 주세요."
                    );
                }
            },
            true
        );

        // 우클릭 메뉴 차단
        document.addEventListener(
            "contextmenu",
            function(event) {
                event.preventDefault();
            },
            true
        );

        // 붙여넣기 이벤트 자체 차단
        document.addEventListener(
            "paste",
            function(event) {
                event.preventDefault();
                alert(
                    "📢 붙여넣기는 사용할 수 없습니다.\\n직접 입력해 주세요."
                );
            },
            true
        );
        </script>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# 1. 기본 설정 (수정 부분)
# ============================================================

SPREADSHEET_NAME = "중학교_독서포트폴리오_DB"

# AI 평가에 사용할 모델 (최신 버전으로 지정)
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"

# 학습지 사진 OCR 전용 모델
OCR_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite"
]

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
    "평가일",
    "평가설정ID",
    "학년도",
    "학기"
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
# 3. 다중 API 키 지원 및 자동 전환(Fallback) Gemini 클라이언트
# ============================================================

def get_gemini_clients():
    """Streamlit Secrets의 GEMINI_API_KEYS 리스트에서 Client 객체들을 생성합니다."""
    try:
        keys = st.secrets.get("GEMINI_API_KEYS", [])

        if not keys and "GEMINI_API_KEY" in st.secrets:
            keys = [st.secrets["GEMINI_API_KEY"]]

        if not keys:
            raise Exception("GEMINI_API_KEYS를 Streamlit Secrets에서 찾지 못했습니다.")

        clients = []
        for k in keys:
            api_key = str(k).strip().strip('"').strip("'")

            if api_key.startswith("{") or "private_key" in api_key:
                raise Exception(
                    "API Key에 Google Cloud 서비스 계정 JSON이 입력되었습니다. "
                    "Google AI Studio(aistudio.google.com)에서 발급받은 API Key(AIzaSy...)를 입력해 주세요."
                )

            if api_key:
                clients.append(genai.Client(api_key=api_key))

        if not clients:
            raise Exception("유효한 Gemini API 키가 없습니다.")

        return clients

    except Exception as e:
        raise Exception(f"Gemini 설정 확인 필요: {e}")


def get_gemini_client():
    """기본 Gemini 클라이언트를 가져옵니다."""
    clients = get_gemini_clients()
    return clients[0]


def generate_with_fallback(contents, config=None, model=GEMINI_MODEL):
    """첫 번째 키로 시도 후, 사용량 초과(429) 발생 시 다음 키로 자동 전환합니다."""
    clients = get_gemini_clients()
    last_error = None

    for idx, client in enumerate(clients):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
        except Exception as e:
            last_error = e
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                st.warning(f"⚠️ API 키 #{idx+1} 사용량 초과. 다음 키로 자동 전환하여 재시도합니다...")
                continue
            else:
                raise e

    raise Exception(f"모든 API 키의 사용 한도가 초과되었습니다. (마지막 에러: {last_error})")


def run_worksheet_ocr(uploaded_files):
    if not uploaded_files:
        raise Exception("학습지 사진을 먼저 선택해 주세요.")

    client = get_gemini_client()

    prompt = r"""
너는 중학교 독서 포트폴리오 학습지의 손글씨를 읽어
웹 입력창에 넣어 주는 OCR 보조 AI이다.

사진은 다음과 같은 고정 양식의 학습지이다.

1) 책 제목
2) 작가
3) 읽은 페이지: '쪽 ~ 쪽' 형태
4) 오늘 읽은 내용 요약
5) 인상 깊은 구절(장면)
6) 그 구절(장면)을 고른 까닭
7) 궁금한 것을 질문하고 답 예측 - 질문
8) 궁금한 것을 질문하고 답 예측 - 답
9) 나의 감상, 느낌

학습지 오른쪽 위의 '교사 확인', '출판사' 등 학생 작성용이 아닌 영역은 무시한다.
'읽은 날'은 사진에서 읽지 말고 프로그램에서 현재 날짜를 사용하므로 반환하지 않는다.

중요한 규칙:
- 사진에 실제로 보이는 학생의 글만 옮긴다. 내용을 요약하거나 고쳐 쓰거나 문장을 자연스럽게 바꾸지 않는다.
- 손글씨가 불분명하면 추측하지 말고 가능한 범위에서 그대로 읽는다.
- 빈칸은 빈 문자열로 반환한다.
- 책 제목, 작가, 페이지 범위도 사진에 실제로 적힌 내용을 우선한다.
- 페이지의 '쪽' 글자는 제외하고 숫자와 범위를 중심으로 반환한다. 예: '35 ~ 58쪽' -> '35~58'
- 여러 장의 사진이 있다면 같은 학습지의 이어지는 부분으로 보고 내용을 합친다.
- '구절(장면)'과 '까닭'은 반드시 분리한다.
- 질문과 답도 반드시 분리한다.
- OCR 결과에 설명이나 마크다운을 넣지 말고 JSON 형식으로만 반환한다.
"""

    schema = {
        "type": "OBJECT",
        "properties": {
            "book_title": {"type": "STRING"},
            "author": {"type": "STRING"},
            "pages_read": {"type": "STRING"},
            "summary": {"type": "STRING"},
            "quote": {"type": "STRING"},
            "quote_reason": {"type": "STRING"},
            "question": {"type": "STRING"},
            "answer": {"type": "STRING"},
            "reflection": {"type": "STRING"}
        },
        "required": [
            "book_title",
            "author",
            "pages_read",
            "summary",
            "quote",
            "quote_reason",
            "question",
            "answer",
            "reflection"
        ]
    }

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema
    )

    contents = [prompt]

    for uploaded_file in uploaded_files:
        contents.append(
            types.Part.from_bytes(
                data=uploaded_file.getvalue(),
                mime_type=uploaded_file.type or "image/jpeg"
            )
        )

    def is_retryable_503(error):
        error_text = str(error).upper()
        return (
            "503" in error_text
            or "UNAVAILABLE" in error_text
            or "SERVICE_UNAVAILABLE" in error_text
        )

    last_error = None

    for model_name in OCR_MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )

                if not response.text:
                    raise Exception("Gemini가 빈 응답을 반환했습니다.")

                result = json.loads(response.text)

                quote = str(result.get("quote", "")).strip()
                quote_reason = str(result.get("quote_reason", "")).strip()

                if quote and quote_reason:
                    combined_quote = f"구절(장면): {quote}\n\n까닭: {quote_reason}"
                elif quote:
                    combined_quote = f"구절(장면): {quote}"
                elif quote_reason:
                    combined_quote = f"까닭: {quote_reason}"
                else:
                    combined_quote = ""

                return {
                    "book_title": str(result.get("book_title", "")).strip(),
                    "author": str(result.get("author", "")).strip(),
                    "pages_read": str(result.get("pages_read", "")).strip(),
                    "summary": str(result.get("summary", "")).strip(),
                    "quote": combined_quote,
                    "question": str(result.get("question", "")).strip(),
                    "answer": str(result.get("answer", "")).strip(),
                    "reflection": str(result.get("reflection", "")).strip()
                }

            except Exception as e:
                last_error = e

                if not is_retryable_503(e):
                    raise

                if attempt < 2:
                    time.sleep(2 ** attempt * 2)

    raise Exception(
        "Gemini 서버가 현재 매우 혼잡하여 학습지 OCR을 처리하지 못했습니다. "
        "잠시 후 다시 시도해 주세요. "
        f"(마지막 오류: {last_error})"
    )


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

def update_reading_log(ws, sheet_row, book_title, author, pages_read, summary, quote, question_text, answer_text, reflection):
    ws.update(
        f"G{sheet_row}:O{sheet_row}",
        [[
            book_title,
            author,
            safe_str(ws.cell(sheet_row, 9).value),
            pages_read,
            summary,
            quote,
            question_text,
            answer_text,
            reflection
        ]],
        value_input_option="USER_ENTERED"
    )


def delete_reading_log(ws, sheet_row):
    ws.delete_rows(sheet_row)


def is_reading_log_editable(log_date, today_str):
    log_date = safe_str(log_date).strip()
    today_str = safe_str(today_str).strip()

    if not log_date or not today_str:
        return False

    log_date_only = log_date[:10]
    return log_date_only == today_str


def get_current_school_year(target_date=None):
    if target_date is None:
        target_date = date.today()
    return target_date.year if target_date.month >= 3 else target_date.year - 1


def get_current_semester(target_date=None):
    if target_date is None:
        target_date = date.today()
    return 1 if 3 <= target_date.month <= 8 else 2


def safe_str(value):
    if pd.isna(value):
        return ""
    return str(value)


def normalize_grade_value(value):
    text = safe_str(value).strip()
    if text.endswith("학년"):
        text = text[:-2]
    return text


@st.cache_data(ttl=30, show_spinner=False)
def read_evaluation_settings():
    records = read_sheet_records("setting")
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df.columns = [
        str(c).replace("\ufeff", "").strip()
        for c in df.columns
    ]
    if "평가설정ID" not in df.columns and "평가ID" in df.columns:
        df = df.rename(columns={"평가ID": "평가설정ID"})

    required = [
        "평가설정ID", "학년도", "학기", "학년", "평가명", "총차시",
        "기준ID", "평가기준", "배점",
        "매우우수점수", "우수점수", "보통점수", "노력요함점수",
        "매우우수 설명", "우수 설명", "보통 설명", "노력요함 설명"
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df[required].copy()


def get_assessment_list():
    df = read_evaluation_settings()
    if df.empty:
        return []
    result = []
    seen = set()
    for _, row in df.iterrows():
        assessment_id = safe_str(row["평가설정ID"]).strip()
        if not assessment_id or assessment_id in seen:
            continue
        seen.add(assessment_id)
        result.append({
            "평가설정ID": assessment_id,
            "학년도": safe_str(row["학년도"]),
            "학기": safe_str(row["학기"]),
            "학년": safe_str(row["학년"]),
            "평가명": safe_str(row["평가명"]),
            "총차시": safe_str(row["총차시"]),
        })
    return result


def get_assessment_rubric(assessment_id):
    df = read_evaluation_settings()
    if df.empty:
        return pd.DataFrame()
    return df[
        df["평가설정ID"].astype(str).str.strip()
        == str(assessment_id).strip()
    ].copy()


def rubric_score_options(row):
    values = []
    for col in ["매우우수점수", "우수점수", "보통점수", "노력요함점수"]:
        try:
            value = int(float(safe_str(row.get(col)).strip()))
            if value not in values:
                values.append(value)
        except Exception:
            pass
    return values


def get_submission_criterion(rubric_df):
    if rubric_df is None or rubric_df.empty:
        return None
    for _, row in rubric_df.iterrows():
        criterion = safe_str(row.get("평가기준")).strip()
        if "작성 횟수" in criterion or "작성횟수" in criterion:
            return row
    return None


def get_submission_score(count, rubric_df):
    row = get_submission_criterion(rubric_df)
    if row is None:
        if count >= 15:
            return 25
        elif count >= 12:
            return 20
        elif count >= 9:
            return 15
        return 10

    total_sessions = 0
    try:
        total_sessions = int(float(safe_str(row.get("총차시")) or 0))
    except Exception:
        pass

    if not total_sessions:
        try:
            total_sessions = int(float(safe_str(
                rubric_df.iloc[0].get("총차시")
            ) or 0))
        except Exception:
            total_sessions = 0

    missing = max(total_sessions - count, 0)

    levels = [
        ("매우 우수", "매우우수점수", safe_str(row.get("매우우수 설명"))),
        ("우수", "우수점수", safe_str(row.get("우수 설명"))),
        ("보통", "보통점수", safe_str(row.get("보통 설명"))),
        ("노력 요함", "노력요함점수", safe_str(row.get("노력요함 설명"))),
    ]

    def score_of(col):
        try:
            return int(float(safe_str(row.get(col))))
        except Exception:
            return 0

    if total_sessions and count >= total_sessions:
        return score_of("매우우수점수")

    import re
    for label, score_col, desc in levels[1:]:
        m = re.search(r"(\d+)\s*[~～-]\s*(\d+)\s*회\s*누락", desc)
        if m and int(m.group(1)) <= missing <= int(m.group(2)):
            return score_of(score_col)

        m = re.search(r"(\d+)\s*회\s*이상\s*누락", desc)
        if m and missing >= int(m.group(1)):
            return score_of(score_col)

    scores = {
        "매우 우수": score_of("매우우수점수"),
        "우수": score_of("우수점수"),
        "보통": score_of("보통점수"),
        "노력 요함": score_of("노력요함점수"),
    }
    if missing <= 0:
        return scores["매우 우수"]
    if missing <= 2:
        return scores["우수"]
    if missing <= 4:
        return scores["보통"]
    return scores["노력 요함"]


def get_submission_level(count, rubric_df):
    row = get_submission_criterion(rubric_df)
    score = get_submission_score(count, rubric_df)
    if row is None:
        if count >= 15:
            return "매우 우수"
        elif count >= 12:
            return "우수"
        elif count >= 9:
            return "보통"
        return "노력 요함"

    total_sessions = 0
    try:
        total_sessions = int(float(safe_str(
            rubric_df.iloc[0].get("총차시")
        ) or 0))
    except Exception:
        pass
    missing = max(total_sessions - count, 0)

    if total_sessions and count >= total_sessions:
        return "매우 우수"
    if missing <= 2:
        return "우수"
    if missing <= 4:
        return "보통"
    return "노력 요함"


def make_evaluation_id(grade, class_name, student_id):
    return f"{grade}_{class_name}_{student_id}"


def ensure_score_sheet():
    ws = get_worksheet("portfolio_scores")

    current_headers = [
        str(h).replace("\ufeff", "").strip()
        for h in read_sheet_headers("portfolio_scores")
    ]

    if not current_headers:
        ws.append_row(SCORE_HEADERS)
        return ws

    normalized_headers = normalize_header_names(current_headers)
    missing = [h for h in SCORE_HEADERS if h not in normalized_headers]

    if missing:
        current_count = len(current_headers)
        for header in missing:
            ws.update_cell(1, current_count + 1, header)
            current_count += 1
        read_sheet_headers.clear()

    return ws


def normalize_header_names(headers):
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
        "평가설정ID": "평가설정ID",
        "학년도": "학년도",
        "학기": "학기",
    }

    result = []
    for h in headers:
        text = str(h).replace("\ufeff", "").strip()
        compact = text.replace(" ", "").replace("_", "")
        result.append(canonical.get(compact, text))

    return result


def normalize_score_dataframe(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=SCORE_HEADERS)

    df = df.copy()
    df.columns = normalize_header_names(df.columns)

    for col in SCORE_HEADERS:
        if col not in df.columns:
            df[col] = ""

    return df[SCORE_HEADERS].copy()


def find_existing_evaluation(ws, evaluation_id, assessment_id=None):
    records = read_sheet_records("portfolio_scores")

    if not records:
        return None, None

    df = normalize_score_dataframe(pd.DataFrame(records))

    matches = df[
        df["평가ID"].astype(str).str.strip() == str(evaluation_id).strip()
    ]

    if assessment_id:
        matches = matches[
            matches["평가설정ID"].astype(str).str.strip()
            == str(assessment_id).strip()
        ]

    if matches.empty:
        return None, None

    row_index = matches.index[0] + 2

    return matches.iloc[0], row_index


# ============================================================
# 6. AI 평가 함수
# ============================================================

def run_ai_evaluation(student_name, book_records, rubric_df):
    client = get_gemini_client()

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

    if rubric_df is None or rubric_df.empty:
        raise Exception("선택된 평가의 루브릭을 setting 시트에서 찾을 수 없습니다.")

    criteria_rows = []
    for _, row in rubric_df.iterrows():
        criterion = safe_str(row.get("평가기준")).strip()
        if "작성 횟수" in criterion or "작성횟수" in criterion:
            continue
        criteria_rows.append(row)

    if not criteria_rows:
        raise Exception("AI가 평가할 루브릭 기준이 없습니다.")

    rubric_parts = []
    for idx, row in enumerate(criteria_rows, start=1):
        criterion = safe_str(row.get("평가기준"))
        max_score = safe_str(row.get("배점"))
        rubric_parts.append(
            f"""[{idx}. {criterion} / 배점 {max_score}점]

매우 우수 ({safe_str(row.get("매우우수점수"))}점):
{safe_str(row.get("매우우수 설명"))}

우수 ({safe_str(row.get("우수점수"))}점):
{safe_str(row.get("우수 설명"))}

보통 ({safe_str(row.get("보통점수"))}점):
{safe_str(row.get("보통 설명"))}

노력 요함 ({safe_str(row.get("노력요함점수"))}점):
{safe_str(row.get("노력요함 설명"))}
"""
        )

    rubric_text = "\n".join(rubric_parts)

    system_prompt = f"""
너는 중학교 국어 교사의 독서 포트폴리오 수행평가를
보조하는 평가 AI이다.

학생의 전체 누적 독서 기록을 아래의 '선택된 평가 루브릭'에
따라 평가 점수를 추천한다.

중요한 원칙:
1. 학생의 실제 작성 내용에 근거해서만 판단한다.
2. 기록에 없는 내용을 추측하지 않는다.
3. 학생의 글쓰기 능력 자체가 아니라 제시된 평가기준을 적용한다.
4. 각 기준에서는 반드시 해당 기준에 제시된 네 점수 중 하나만 선택한다.
5. 작성 횟수 기준은 AI가 평가하지 않는다. 프로그램이 실제 제출 횟수로 계산한다.
6. AI 평가는 최종 성적이 아니라 교사가 검토할 수 있는 추천 평가이다.
7. 평가 근거에는 학생 기록에서 확인되는 구체적인 내용이 포함되어야 한다.
8. 근거 없는 칭찬이나 비판을 하지 않는다.

선택된 평가 루브릭:
{rubric_text}
"""

    user_prompt = f"""
학생 이름: {student_name}

이 학생의 누적 독서 포트폴리오 기록:
{records_text}

위 자료를 선택된 루브릭에 따라 평가하라.
각 기준별 점수와 평가 근거를 제시하라.
종합피드백은 교사가 평가 결과를 참고할 수 있는 형태로 작성한다.
"""

    criteria = criteria_rows[:3]
    if len(criteria) < 3:
        raise Exception(
            "현재 portfolio_scores 구조는 AI 평가 기준을 3개 저장합니다. "
            "setting 시트에는 작성 횟수를 제외한 AI 평가 기준이 최소 3개 필요합니다."
        )

    score_enums = []
    for row in criteria:
        options = rubric_score_options(row)
        if not options:
            raise Exception(
                f"'{safe_str(row.get('평가기준'))}'의 점수 설정을 확인해 주세요."
            )
        score_enums.append([str(v) for v in options])

    key_defs = [
        ("기준1_점수", score_enums[0]),
        ("기준2_점수", score_enums[1]),
        ("기준3_점수", score_enums[2]),
        ("기준1_근거", None),
        ("기준2_근거", None),
        ("기준3_근거", None),
        ("종합피드백", None),
    ]

    properties = {}
    for key, enum_values in key_defs:
        if enum_values is None:
            properties[key] = {"type": "STRING"}
        else:
            properties[key] = {"type": "STRING", "enum": enum_values}

    schema = {
        "type": "OBJECT",
        "properties": properties,
        "required": list(properties.keys())
    }

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema
    )

    contents = [system_prompt, user_prompt]

    def generate_with_retry(model_name, attempts=4):
        last_error = None
        for attempt in range(attempts):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                last_error = e
                error_text = str(e)
                is_retryable = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "service_unavailable" in error_text
                )
                if not is_retryable or attempt >= attempts - 1:
                    raise
                time.sleep(3 * (2 ** attempt))
        raise last_error

    try:
        response = generate_with_retry(GEMINI_MODEL)
    except Exception as primary_error:
        primary_text = str(primary_error)
        if (
            "503" in primary_text
            or "UNAVAILABLE" in primary_text
            or "service_unavailable" in primary_text
        ):
            response = generate_with_retry(GEMINI_FALLBACK_MODEL, attempts=2)
        else:
            raise

    if not response.text:
        raise Exception("Gemini가 빈 응답을 반환했습니다.")

    result = json.loads(response.text)

    scores = []
    for idx, row in enumerate(criteria, start=1):
        value = int(result[f"기준{idx}_점수"])
        allowed = set(rubric_score_options(row))
        if value not in allowed:
            raise Exception(
                f"Gemini 평가 점수가 루브릭과 일치하지 않습니다: {value}"
            )
        scores.append(value)

    return {
        "understanding": scores[0],
        "completeness": scores[1],
        "depth": scores[2],
        "reason": (
            f"① {safe_str(criteria[0].get('평가기준'))}\n"
            f"{result['기준1_근거']}\n\n"
            f"② {safe_str(criteria[1].get('평가기준'))}\n"
            f"{result['기준2_근거']}\n\n"
            f"③ {safe_str(criteria[2].get('평가기준'))}\n"
            f"{result['기준3_근거']}"
        ),
        "feedback": result["종합피드백"]
    }


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
    teacher_feedback,
    assessment_id="",
    assessment_year="",
    assessment_semester=""
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        now,
        assessment_id,
        assessment_year,
        assessment_semester
    ]

    existing, row_index = find_existing_evaluation(
        ws,
        evaluation_id,
        assessment_id
    )

    if row_index is None:
        ws.append_row(
            row_values,
            value_input_option="USER_ENTERED"
        )
    else:
        ws.update(
            f"A{row_index}:V{row_index}",
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

    if "logged_in_student" not in st.session_state:
        with st.form("student_login_form"):
            st.markdown("### 🔑 학생 로그인")

            try:
                _student_records_for_year = read_sheet_records("student_list")
                _student_years = sorted({
                    safe_str(r.get("학년도")).strip()
                    for r in _student_records_for_year
                    if safe_str(r.get("학년도")).strip()
                }, reverse=True)
            except Exception:
                _student_years = []

            if not _student_years:
                _student_years = [str(get_current_school_year())]

            default_year = str(get_current_school_year())
            if default_year not in _student_years:
                default_year = _student_years[0]

            c0, c1, c2, c3, c4 = st.columns(5)

            with c0:
                school_year = st.selectbox(
                    "학년도",
                    _student_years,
                    index=_student_years.index(default_year),
                    key="s_school_year"
                )

            with c1:
                grade = st.selectbox(
                    "학년",
                    ["1학년", "2학년", "3학년"],
                    key="s_grade"
                )

            with c2:
                class_name = st.selectbox(
                    "반",
                    ["1반", "2반", "3반", "4반", "5반", "6반", "7반", "8반"],
                    key="s_class"
                )

            with c3:
                student_id = st.text_input("번호", key="s_id")

            with c4:
                pin = st.text_input("고유번호 (PIN 4자리)", type="password", key="s_pin")

            login_btn = st.form_submit_button(
                "🚀 학생 포트폴리오 입장하기",
                use_container_width=True
            )

        if login_btn:
            if not student_id or not pin:
                st.warning("⚠️ 번호와 고유번호를 모두 입력해 주세요.")
            else:
                try:
                    ws_std = get_worksheet("student_list")
                    df_std = pd.DataFrame(read_sheet_records("student_list"))

                    selected_school_year = str(school_year).strip()
                    if "학년도" in df_std.columns:
                        df_std = df_std[
                            df_std["학년도"].astype(str).str.strip()
                            == selected_school_year
                        ]

                    user_match = df_std[
                        (df_std["학년"].astype(str) == str(grade)) &
                        (df_std["반"].astype(str) == str(class_name)) &
                        (df_std["번호"].astype(str) == str(student_id)) &
                        (df_std["고유번호"].astype(str) == str(pin))
                    ]

                    if user_match.empty:
                        st.error("❌ 학년, 반, 번호 또는 고유번호가 일치하지 않습니다.")
                    else:
                        st.session_state["logged_in_student"] = {
                            "grade": grade,
                            "class_name": class_name,
                            "student_id": student_id,
                            "student_name": user_match.iloc[0]["이름"],
                            "school_year": int(selected_school_year) if selected_school_year.isdigit() else selected_school_year
                        }
                        st.rerun()

                except Exception as e:
                    st.error(f"구글 시트 연결 오류: {e}")

    else:
        std_info = st.session_state["logged_in_student"]

        s_grade = std_info["grade"]
        s_class = std_info["class_name"]
        s_id = std_info["student_id"]
        s_name = std_info["student_name"]
        s_school_year = std_info.get("school_year", get_current_school_year())

        c_top1, c_top2 = st.columns([4, 1])

        with c_top1:
            st.success(
                f"👋 [{s_grade} {s_class} {s_id}번] "
                f"{s_name} 학생 환영합니다!"
            )

        with c_top2:
            if st.button("로그아웃", use_container_width=True):
                del st.session_state["logged_in_student"]
                st.rerun()

        today_str = date.today().strftime("%Y-%m-%d")

        try:
            ws_dates = get_worksheet("allowed_class_dates")
            df_dates = pd.DataFrame(read_sheet_records("allowed_class_dates"))

            grade_col = "학년" if "학년" in df_dates.columns else "grade"
            class_col = "반" if "반" in df_dates.columns else "class_name"
            date_col = "날짜" if "날짜" in df_dates.columns else "allowed_date"
            session_col = "차시" if "차시" in df_dates.columns else "session_num"

            current_semester = get_current_semester()
            date_mask = (
                (df_dates[grade_col].astype(str) == str(s_grade)) &
                (df_dates[class_col].astype(str) == str(s_class)) &
                (df_dates[date_col].astype(str).str[:10] == str(today_str))
            )

            if "학년도" in df_dates.columns:
                date_mask &= (
                    df_dates["학년도"].astype(str).str.strip()
                    == str(s_school_year)
                )
            if "학기" in df_dates.columns:
                date_mask &= (
                    df_dates["학기"].astype(str).str.strip()
                    == str(current_semester)
                )

            date_record = df_dates[date_mask]

        except Exception:
            date_record = pd.DataFrame()

        tab1, tab2 = st.tabs(["📝 오늘의 독서 기록 쓰기", "📖 내 과거 기록 보기"])

        with tab1:
            if date_record.empty:
                st.error(
                    f"⛔ [{s_grade} {s_class}]은(는) "
                    f"오늘({today_str}) 독서 기록 작성 허용 날짜가 아닙니다."
                )
            else:
                session_name = date_record.iloc[0][session_col]

                st.info(f"📌 현재 진행 차시: {s_grade} {s_class} - {session_name}")

                st.markdown("### 📷 종이 학습지로 자동 입력")
                st.caption(
                    "학습지를 작성한 뒤 사진을 올리면, 사진 속 내용을 읽어 "
                    "아래 입력칸에 자동으로 넣어 줍니다. OCR 결과는 반드시 확인·수정한 뒤 제출하세요."
                )

                worksheet_files = st.file_uploader(
                    "학습지 사진 선택 (JPG, JPEG, PNG)",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key="worksheet_ocr_files"
                )

                if st.button(
                    "🔍 학습지 사진에서 내용 불러오기",
                    use_container_width=True,
                    type="secondary",
                    key="worksheet_ocr_button"
                ):
                    if not worksheet_files:
                        st.warning("먼저 학습지 사진을 선택해 주세요.")
                    else:
                        try:
                            with st.spinner("🔍 학습지의 손글씨를 읽고 있습니다..."):
                                ocr_result = run_worksheet_ocr(worksheet_files)

                            st.session_state["reading_book_title"] = ocr_result["book_title"]
                            st.session_state["reading_author"] = ocr_result["author"]
                            st.session_state["reading_pages"] = ocr_result["pages_read"]
                            st.session_state["reading_summary"] = ocr_result["summary"]
                            st.session_state["reading_quote"] = ocr_result["quote"]
                            st.session_state["reading_question"] = ocr_result["question"]
                            st.session_state["reading_answer"] = ocr_result["answer"]
                            st.session_state["reading_reflection"] = ocr_result["reflection"]

                            st.session_state["worksheet_ocr_done"] = True
                            st.rerun()

                        except Exception as e:
                            st.error(f"학습지 OCR 처리 중 오류가 발생했습니다: {e}")

                if st.session_state.get("worksheet_ocr_done", False):
                    st.success("✅ 학습지 내용을 입력창에 불러왔습니다. 내용을 확인·수정한 뒤 제출하세요.")

                with st.form("reading_form"):
                    col_b1, col_b2 = st.columns(2)

                    with col_b1:
                        book_title = st.text_input("책 제목 *", key="reading_book_title")
                        author = st.text_input("작가 이름 *", key="reading_author")

                    with col_b2:
                        pages_read = st.text_input("오늘 읽은 페이지 범위 (예: 12~35p) *", key="reading_pages")

                    summary = st.text_area("1. 오늘 읽은 내용 짧은 요약 (핵심 줄거리) *", height=110, key="reading_summary")
                    quote = st.text_area("2. 가장 인상 깊은 문장과 이유", height=90, key="reading_quote")

                    st.markdown("##### 3. 읽은 내용을 바탕으로 만든 질문과 답변")
                    col_q1, col_q2 = st.columns(2)

                    with col_q1:
                        question_text = st.text_area(
                            "3-1. 나의 질문",
                            height=100,
                            placeholder="예: 주인공은 왜 그런 선택을 했을까?",
                            key="reading_question"
                        )

                    with col_q2:
                        answer_text = st.text_area(
                            "3-2. 질문에 대한 나의 생각/답변",
                            height=100,
                            placeholder="예: 자신의 가치관을 지키기 위해서였을 것이다.",
                            key="reading_answer"
                        )

                    reflection = st.text_area("4. 나의 생각과 느낌 (느낀점/깨달은점) *", height=130, key="reading_reflection")

                    submit_btn = st.form_submit_button("🚀 독서 기록 제출하기", use_container_width=True)

                    if submit_btn:
                        if not book_title or not pages_read or not summary or not reflection:
                            st.error("필수 항목(*)을 빠짐없이 입력해 주세요!")
                        else:
                            ws_logs = get_worksheet("reading_logs")
                            ws_logs.append_row([
                                str(s_school_year),
                                str(get_current_semester()),
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
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ])

                            st.cache_data.clear()
                            st.balloons()
                            st.success("오늘의 독서 기록이 구글 시트에 안전하게 제출되었습니다!")
                            st.session_state["worksheet_ocr_done"] = False

        with tab2:
            try:
                ws_logs = get_worksheet("reading_logs")
                df_logs = pd.DataFrame(read_sheet_records("reading_logs"))

                if not df_logs.empty:
                    my_logs = df_logs[
                        (df_logs["학년"].astype(str) == str(s_grade)) &
                        (df_logs["반"].astype(str) == str(s_class)) &
                        (df_logs["번호"].astype(str) == str(s_id))
                    ]
                    if "학년도" in df_logs.columns:
                        my_logs = my_logs[
                            my_logs["학년도"].astype(str).str.strip()
                            == str(s_school_year)
                        ]

                    if my_logs.empty:
                        st.info("아직 제출된 기록이 없습니다.")
                    else:
                        st.caption(
                            "📌 독서 기록은 작성 허용 날짜 당일에만 수정할 수 있습니다. "
                            "허용 날짜가 지나면 수정은 불가능하며 삭제만 할 수 있습니다."
                        )

                        editing_row = st.session_state.get("editing_reading_log_row")
                        deleting_row = st.session_state.get("deleting_reading_log_row")

                        for row_index, row in my_logs.iterrows():
                            sheet_row = int(row_index) + 2

                            log_date = safe_str(row.get("날짜"))
                            book_title = safe_str(row.get("책 제목"))
                            pages_read = safe_str(row.get("읽은 페이지"))
                            edit_allowed = is_reading_log_editable(log_date, today_str)

                            if not edit_allowed and sheet_row == editing_row:
                                st.session_state.pop("editing_reading_log_row", None)
                                editing_row = None

                            with st.expander(
                                f"📌 [{log_date}] {book_title} ({pages_read})",
                                expanded=(sheet_row == editing_row or sheet_row == deleting_row)
                            ):
                                if sheet_row == deleting_row:
                                    st.warning("⚠️️ 이 독서 기록을 정말 삭제할까요? 삭제하면 다시 복구하기 어렵습니다.")
                                    dc1, dc2 = st.columns(2)

                                    with dc1:
                                        if st.button("🗑️ 삭제하기", type="primary", use_container_width=True, key=f"confirm_delete_{sheet_row}"):
                                            try:
                                                delete_reading_log(ws_logs, sheet_row)
                                                st.cache_data.clear()
                                                st.session_state.pop("deleting_reading_log_row", None)
                                                st.session_state.pop("editing_reading_log_row", None)
                                                st.success("✅ 독서 기록이 삭제되었습니다.")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"기록 삭제 중 오류가 발생했습니다: {e}")

                                    with dc2:
                                        if st.button("취소", use_container_width=True, key=f"cancel_delete_{sheet_row}"):
                                            st.session_state.pop("deleting_reading_log_row", None)
                                            st.rerun()

                                    continue

                                if sheet_row == editing_row and edit_allowed:
                                    st.info("✏️ 잘못 입력한 내용을 수정한 뒤 ‘수정 내용 저장’을 눌러 주세요.")

                                    edit_book_title = st.text_input("책 제목 *", value=book_title, key=f"edit_book_title_{sheet_row}")
                                    edit_author = st.text_input("작가 이름", value=safe_str(row.get("작가")), key=f"edit_author_{sheet_row}")
                                    edit_pages = st.text_input("읽은 페이지 범위 *", value=pages_read, key=f"edit_pages_{sheet_row}")
                                    edit_summary = st.text_area("1. 오늘 읽은 내용 짧은 요약 *", value=safe_str(row.get("요약")), height=120, key=f"edit_summary_{sheet_row}")
                                    edit_quote = st.text_area("2. 가장 인상 깊은 문장과 이유", value=safe_str(row.get("인상깊은 내용")), height=100, key=f"edit_quote_{sheet_row}")
                                    edit_question = st.text_area("3-1. 나의 질문", value=safe_str(row.get("질문")), height=100, key=f"edit_question_{sheet_row}")
                                    edit_answer = st.text_area("3-2. 질문에 대한 나의 생각/답변", value=safe_str(row.get("답변")), height=100, key=f"edit_answer_{sheet_row}")
                                    edit_reflection = st.text_area("4. 나의 생각과 느낌 *", value=safe_str(row.get("느낀점")), height=130, key=f"edit_reflection_{sheet_row}")

                                    ec1, ec2 = st.columns(2)

                                    with ec1:
                                        if st.button("💾 수정 내용 저장", type="primary", use_container_width=True, key=f"save_edit_{sheet_row}"):
                                            if not is_reading_log_editable(log_date, today_str):
                                                st.session_state.pop("editing_reading_log_row", None)
                                                st.error("🔒 수정 가능한 날짜가 지났습니다. 이 기록은 삭제만 할 수 있습니다.")
                                                st.rerun()

                                            if not edit_book_title.strip() or not edit_pages.strip() or not edit_summary.strip() or not edit_reflection.strip():
                                                st.error("필수 항목(*)을 빠짐없이 입력해 주세요.")
                                            else:
                                                try:
                                                    update_reading_log(
                                                        ws_logs,
                                                        sheet_row,
                                                        edit_book_title.strip(),
                                                        edit_author.strip(),
                                                        edit_pages.strip(),
                                                        edit_summary.strip(),
                                                        edit_quote.strip(),
                                                        edit_question.strip(),
                                                        edit_answer.strip(),
                                                        edit_reflection.strip()
                                                    )
                                                    st.cache_data.clear()
                                                    st.session_state.pop("editing_reading_log_row", None)
                                                    st.success("✅ 독서 기록이 수정되었습니다.")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"기록 수정 중 오류가 발생했습니다: {e}")

                                    with ec2:
                                        if st.button("취소", use_container_width=True, key=f"cancel_edit_{sheet_row}"):
                                            st.session_state.pop("editing_reading_log_row", None)
                                            st.rerun()

                                    continue

                                ac1, ac2 = st.columns(2)

                                with ac1:
                                    if edit_allowed:
                                        if st.button("✏️ 수정", use_container_width=True, key=f"edit_log_{sheet_row}"):
                                            st.session_state["editing_reading_log_row"] = sheet_row
                                            st.session_state.pop("deleting_reading_log_row", None)
                                            st.rerun()
                                    else:
                                        st.button("🔒 수정 기간 종료", use_container_width=True, disabled=True, key=f"edit_locked_{sheet_row}")

                                with ac2:
                                    if st.button("🗑️ 삭제", use_container_width=True, key=f"delete_log_{sheet_row}"):
                                        st.session_state["deleting_reading_log_row"] = sheet_row
                                        st.session_state.pop("editing_reading_log_row", None)
                                        st.rerun()

                                if not edit_allowed:
                                    st.caption("🔒 작성 허용 날짜가 지나 이 기록은 수정할 수 없습니다. 필요한 경우 삭제만 할 수 있습니다.")

                                st.write(f"**작가:** {safe_str(row.get('작가'))}")
                                st.write(f"**줄거리 요약:** {safe_str(row.get('요약'))}")
                                st.write(f"**인상 깊은 내용:** {safe_str(row.get('인상깊은 내용'))}")
                                st.write(f"**질문:** {safe_str(row.get('질문'))}")
                                st.write(f"**답변:** {safe_str(row.get('답변'))}")
                                st.write(f"**느낀점:** {safe_str(row.get('느낀점'))}")

            except Exception as e:
                st.error(f"기록 조회 오류: {e}")


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

    if "teacher_logged_in" not in st.session_state:
        st.session_state["teacher_logged_in"] = False

    if not st.session_state["teacher_logged_in"]:
        with st.sidebar.form("teacher_login_form"):
            st.markdown("### 🔐 교사 로그인")
            teacher_pw = st.text_input("교사용 비밀번호", type="password")
            teacher_login_btn = st.form_submit_button("확인", use_container_width=True)

        if teacher_login_btn:
            if teacher_pw == "0923":
                st.session_state["teacher_logged_in"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 올바르지 않습니다.")

        st.info("교사용 화면을 이용하려면 교사 비밀번호를 입력해 주세요.")
        st.stop()

    st.sidebar.success("✅ 교사 로그인 상태")

    teacher_logout_btn = st.sidebar.button("🚪 로그아웃", use_container_width=True)
    if teacher_logout_btn:
        st.session_state["teacher_logged_in"] = False
        st.rerun()

    teacher_menu = st.sidebar.radio(
        "관리 메뉴",
        ["📊 평가 관리", "⚙️ 평가 설정"],
        key="teacher_menu"
    )

    try:
        assessment_list = get_assessment_list()
    except Exception as e:
        st.error(f"평가 설정 시트를 읽을 수 없습니다: {e}")
        st.stop()

    if teacher_menu == "⚙️ 평가 설정":
        st.markdown("### ⚙️ 평가 설정")
        st.caption(
            "Google Sheet의 'setting' 시트를 기준으로 학년도·학기·학년별 평가 루브릭을 관리합니다. "
            "이 화면에서 확인한 평가가 AI 자동 채점에 그대로 적용됩니다."
        )

        if st.button("🔄 Google Sheets 설정 새로고침", key="refresh_setting", use_container_width=False):
            read_sheet_records.clear()
            read_sheet_headers.clear()
            read_evaluation_settings.clear()
            st.rerun()

        if not assessment_list:
            st.error("setting 시트에 평가 설정이 없습니다. 평가설정ID부터 루브릭 기준까지 입력해 주세요.")
            st.stop()

        setting_df = read_evaluation_settings()

        for item in assessment_list:
            with st.expander(
                f"📚 {item['평가설정ID']} · {item['평가명']} "
                f"({item['학년도']}학년도 {item['학기']}학기 / {item['학년']}학년)",
                expanded=False
            ):
                st.write(f"**총차시:** {item['총차시']}차시")
                rubric_view = setting_df[
                    setting_df["평가설정ID"].astype(str).str.strip() == item["평가설정ID"]
                ].copy()

                show_cols = [
                    "기준ID", "평가기준", "배점",
                    "매우우수점수", "우수점수", "보통점수", "노력요함점수",
                    "매우우수 설명", "우수 설명", "보통 설명", "노력요함 설명"
                ]
                st.dataframe(rubric_view[show_cols], use_container_width=True, hide_index=True)

        st.info("💡 루브릭 내용을 변경할 때는 Google Sheet의 'setting' 시트만 수정하면 됩니다.")
        st.stop()

    if not assessment_list:
        st.error("setting 시트에 평가 설정이 없습니다. 교사 → 평가 설정 메뉴에서 먼저 확인해 주세요.")
        st.stop()

    assessment_labels = []
    assessment_map = {}
    for item in assessment_list:
        label = (
            f"{item['평가설정ID']} | {item['평가명']} | "
            f"{item['학년도']}학년도 {item['학기']}학기 | "
            f"{item['학년']}학년 | {item['총차시']}차시"
        )
        assessment_labels.append(label)
        assessment_map[label] = item

    saved_assessment = st.session_state.get("active_assessment_label")
    if saved_assessment not in assessment_labels:
        saved_assessment = assessment_labels[0]

    active_assessment_label = st.sidebar.selectbox(
        "현재 평가",
        assessment_labels,
        index=assessment_labels.index(saved_assessment),
        key="active_assessment_label"
    )
    active_assessment = assessment_map[active_assessment_label]
    active_assessment_id = active_assessment["평가설정ID"]
    active_rubric = get_assessment_rubric(active_assessment_id)

    if active_rubric.empty:
        st.error(f"선택한 평가설정ID '{active_assessment_id}'의 루브릭을 찾을 수 없습니다.")
        st.stop()

    st.sidebar.caption(
        f"📌 적용 루브릭: {active_assessment['평가명']} / "
        f"{active_assessment['학년도']}-{active_assessment['학기']}"
    )

    try:
        ws_logs = get_worksheet("reading_logs")
        df_logs = pd.DataFrame(read_sheet_records("reading_logs"))

        ws_std = get_worksheet("student_list")
        df_std = pd.DataFrame(read_sheet_records("student_list"))

        if "학년도" in df_std.columns:
            df_std = df_std[
                df_std["학년도"].astype(str).str.strip()
                == str(active_assessment["학년도"]).strip()
            ].copy()

        if not df_logs.empty:
            if "학년도" in df_logs.columns:
                df_logs = df_logs[
                    df_logs["학년도"].astype(str).str.strip()
                    == str(active_assessment["학년도"]).strip()
                ].copy()
            if "학기" in df_logs.columns:
                df_logs = df_logs[
                    df_logs["학기"].astype(str).str.strip()
                    == str(active_assessment["학기"]).strip()
                ].copy()

        ws_scores = ensure_score_sheet()
        score_records = read_sheet_records("portfolio_scores")

        if score_records:
            df_scores = pd.DataFrame(score_records)
        else:
            df_scores = pd.DataFrame(columns=SCORE_HEADERS)

        df_scores = normalize_score_dataframe(df_scores)

    except Exception as e:
        st.error(f"구글 시트 읽기 오류: {e}")
        st.stop()

    total_students = len(df_std)

    if not df_logs.empty:
        submitted_students = df_logs[["학년", "반", "번호"]].drop_duplicates().shape[0]
        total_records = len(df_logs)
    else:
        submitted_students = 0
        total_records = 0

    if not df_scores.empty:
        completed_evaluations = len(
            df_scores[
                (df_scores["최종점수"].astype(str).str.strip() != "") &
                (df_scores["평가설정ID"].astype(str).str.strip() == active_assessment_id)
            ]
        )
    else:
        completed_evaluations = 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("등록 학생", f"{total_students}명")
    with col2:
        st.metric("제출 학생", f"{submitted_students}명")
    with col3:
        st.metric("전체 독서 기록", f"{total_records}회")
    with col4:
        st.metric("평가 완료", f"{completed_evaluations}명")

    st.divider()

    st.info(
        f"📚 현재 적용 평가: **{active_assessment['평가명']}** · "
        f"{active_assessment['학년도']}학년도 {active_assessment['학기']}학기 · "
        f"{active_assessment['학년']}학년 · 총 {active_assessment['총차시']}차시"
    )

    st.markdown("### 🔎 학생 필터")

    f1, f2, f3 = st.columns([1, 1, 2])

    with f1:
        grades = sorted(df_std["학년"].astype(str).unique().tolist()) if not df_std.empty else []
        grade_options = ["전체"] + grades
        selected_grade = st.selectbox("학년", grade_options)

    with f2:
        temp_std = df_std.copy()
        if selected_grade != "전체" and not temp_std.empty:
            temp_std = temp_std[temp_std["학년"].astype(str) == str(selected_grade)]

        classes = sorted(temp_std["반"].astype(str).unique().tolist()) if not temp_std.empty else []
        class_options = ["전체"] + classes
        selected_class = st.selectbox("반", class_options)

    if selected_grade != "전체" and selected_class != "전체":
        st.markdown("### 📊 학급 통계")

        class_students = df_std[
            (df_std["학년"].astype(str) == str(selected_grade)) &
            (df_std["반"].astype(str) == str(selected_class))
        ].copy()

        student_count = len(class_students)
        avg_logs = 0.0

        if not df_logs.empty and student_count > 0:
            class_logs = df_logs[
                (df_logs["학년"].astype(str) == str(selected_grade)) &
                (df_logs["반"].astype(str) == str(selected_class))
            ].copy()

            if not class_logs.empty:
                log_count = class_logs.groupby(class_logs["번호"].astype(str)).size()
                student_ids = class_students["번호"].astype(str).drop_duplicates().tolist()
                log_count = log_count.reindex(student_ids, fill_value=0)
                avg_logs = round(log_count.mean(), 1)

        scored_students = 0
        if not df_scores.empty and student_count > 0:
            class_scores = df_scores[
                (df_scores["학년"].astype(str) == str(selected_grade)) &
                (df_scores["반"].astype(str) == str(selected_class)) &
                (df_scores["평가설정ID"].astype(str).str.strip() == active_assessment_id)
            ].copy()

            if not class_scores.empty:
                class_scores["최종점수_숫자"] = pd.to_numeric(class_scores["최종점수"], errors="coerce")
                scored_students = class_scores[class_scores["최종점수_숫자"].notna()]["번호"].astype(str).nunique()

        complete_rate = round(scored_students / student_count * 100, 1) if student_count > 0 else 0.0

        avg_score = 0.0
        if not df_scores.empty:
            class_scores = df_scores[
                (df_scores["학년"].astype(str) == str(selected_grade)) &
                (df_scores["반"].astype(str) == str(selected_class)) &
                (df_scores["평가설정ID"].astype(str).str.strip() == active_assessment_id)
            ].copy()

            if not class_scores.empty:
                class_scores["최종점수_숫자"] = pd.to_numeric(class_scores["최종점수"], errors="coerce")
                scored_scores = class_scores[class_scores["최종점수_숫자"].notna()]
                if not scored_scores.empty:
                    avg_score = round(scored_scores["최종점수_숫자"].mean(), 1)

        stat1, stat2, stat3 = st.columns(3)
        with stat1:
            st.metric("평균 작성 차시", f"{avg_logs}차시")
        with stat2:
            st.metric("채점 완료율", f"{complete_rate}%")
        with stat3:
            st.metric("평균 점수", f"{avg_score}점")

        st.divider()

    with f3:
        temp_students = df_std.copy()
        if selected_grade != "전체":
            temp_students = temp_students[temp_students["학년"].astype(str) == str(selected_grade)]
        if selected_class != "전체":
            temp_students = temp_students[temp_students["반"].astype(str) == str(selected_class)]

        student_options = ["전체"]
        student_map = {}

        if not temp_students.empty:
            for _, row in temp_students.iterrows():
                student_label = f"{row['번호']}번 {row['이름']}"
                student_options.append(student_label)
                student_map[student_label] = row

        saved_selected_student = st.session_state.get("selected_student_label", "전체")
        if saved_selected_student not in student_options:
            saved_selected_student = "전체"

        st.session_state["teacher_student_select"] = saved_selected_student

        selected_student = st.selectbox(
            "학생",
            student_options,
            key="teacher_student_select"
        )
        st.session_state["selected_student_label"] = selected_student

    if selected_student == "전체":
        st.markdown("### 👥 학생 목록")

        if temp_students.empty:
            st.info("조건에 해당하는 학생이 없습니다.")
        else:
            display_rows = []
            for _, student in temp_students.iterrows():
                grade = safe_str(student["학년"])
                class_name = safe_str(student["반"])
                student_id = safe_str(student["번호"])
                student_name = safe_str(student["이름"])

                count = len(df_logs[
                    (df_logs["학년"].astype(str) == grade) &
                    (df_logs["반"].astype(str) == class_name) &
                    (df_logs["번호"].astype(str) == student_id)
                ]) if not df_logs.empty else 0

                evaluation_id = make_evaluation_id(grade, class_name, student_id)
                final_score = ""

                if not df_scores.empty:
                    score_match = df_scores[
                        (df_scores["평가ID"].astype(str).str.strip() == evaluation_id) &
                        (df_scores["평가설정ID"].astype(str).str.strip() == active_assessment_id)
                    ]
                    if not score_match.empty:
                        final_score = safe_str(score_match.iloc[0]["최종점수"])

                if final_score:
                    status = "✅ 평가완료"
                elif count > 0:
                    status = "🟡 평가대기"
                else:
                    status = "⚪ 미제출"

                display_rows.append({
                    "번호": student_id,
                    "이름": student_name,
                    "학년": grade,
                    "반": class_name,
                    "작성 횟수": count,
                    "작성 점수": get_submission_score(count, active_rubric),
                    "최종 점수": final_score,
                    "상태": status
                })

            display_df = pd.DataFrame(display_rows)
            table_event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="student_table"
            )

            selected_rows = table_event.selection.rows
            if selected_rows:
                selected_index = selected_rows[0]
                selected_row = display_df.iloc[selected_index]
                selected_label = f"{selected_row['번호']}번 {selected_row['이름']}"
                st.session_state["selected_student_label"] = selected_label
                st.rerun()

    if selected_student != "전체":
        student = student_map[selected_student]
        grade = safe_str(student["학년"])
        class_name = safe_str(student["반"])
        student_id = safe_str(student["번호"])
        student_name = safe_str(student["이름"])

        evaluation_id = make_evaluation_id(grade, class_name, student_id)

        student_logs = df_logs[
            (df_logs["학년"].astype(str) == grade) &
            (df_logs["반"].astype(str) == class_name) &
            (df_logs["번호"].astype(str) == student_id)
        ].copy() if not df_logs.empty else pd.DataFrame()

        submission_count = len(student_logs)
        automatic_count_score = get_submission_score(submission_count, active_rubric)
        count_level = get_submission_level(submission_count, active_rubric)

        existing_evaluation, existing_row_index = find_existing_evaluation(
            ws_scores,
            evaluation_id,
            active_assessment_id
        )

        st.divider()

        header_left, header_right = st.columns([4, 1])

        with header_left:
            st.markdown(
                f"## 👤 {student_name} "
                f"<span style='font-size:16px;color:#6b7280;'>"
                f"({grade} {class_name} {student_id}번)"
                f"</span>",
                unsafe_allow_html=True
            )
            st.caption(f"누적 독서 기록 {submission_count}회")

        with header_right:
            count_level = get_submission_level(submission_count, active_rubric)
            if count_level in ["매우 우수", "우수"]:
                st.success(f"작성 횟수 {submission_count}회 · {count_level}")
            elif count_level == "보통":
                st.warning(f"작성 횟수 {submission_count}회 · {count_level}")
            else:
                st.error(f"작성 횟수 {submission_count}회 · {count_level}")

        left_col, right_col = st.columns([1.25, 1], gap="large")

        with left_col:
            st.markdown("### 📚 제출된 독서 포트폴리오")

            if student_logs.empty:
                st.warning("아직 제출된 독서 기록이 없습니다.")
            else:
                if "날짜" in student_logs.columns:
                    student_logs = student_logs.sort_values(by="날짜")

                for i, (_, row) in enumerate(student_logs.iterrows(), start=1):
                    book_title = safe_str(row.get("책 제목"))
                    log_date = safe_str(row.get("날짜"))

                    with st.expander(
                        f"📖 {i}차시 · {log_date} · {book_title}",
                        expanded=(i == len(student_logs))
                    ):
                        st.markdown(f"**작가:** {safe_str(row.get('작가'))}")
                        st.markdown(f"**읽은 페이지:** {safe_str(row.get('읽은 페이지'))}")
                        st.markdown("#### ① 오늘 읽은 내용 요약")
                        st.write(safe_str(row.get("요약")))
                        st.markdown("#### ② 인상 깊은 내용")
                        st.write(safe_str(row.get("인상깊은 내용")))
                        st.markdown("#### ③ 나의 질문")
                        st.write(safe_str(row.get("질문")))
                        st.markdown("#### ④ 질문에 대한 답변")
                        st.write(safe_str(row.get("답변")))
                        st.markdown("#### ⑤ 나의 생각과 느낌")
                        st.write(safe_str(row.get("느낀점")))

        with right_col:
            st.markdown("### 🤖 AI 수행평가")
            st.info(
                f"현재 평가: **{active_assessment['평가명']}** "
                f"({active_assessment['학년도']}학년도 {active_assessment['학기']}학기)\n\n"
                "AI는 setting 시트의 루브릭에 따라 내용 기준을 평가하고, "
                "작성 횟수는 실제 제출 횟수와 해당 루브릭을 기준으로 자동 계산합니다."
            )

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
                    ai_understanding = int(float(safe_str(existing_evaluation["AI_내용이해"]) or 0))
                    ai_completeness = int(float(safe_str(existing_evaluation["AI_작성충실도"]) or 0))
                    ai_depth = int(float(safe_str(existing_evaluation["AI_감상의깊이"]) or 0))
                    ai_total = int(float(safe_str(existing_evaluation["AI_총점"]) or 0))
                    ai_reason = safe_str(existing_evaluation["AI_평가근거"])
                    ai_feedback = safe_str(existing_evaluation["AI_종합피드백"])

                    teacher_understanding = int(float(safe_str(existing_evaluation["교사_내용이해"]) or ai_understanding or 10))
                    teacher_completeness = int(float(safe_str(existing_evaluation["교사_작성충실도"]) or ai_completeness or 10))
                    teacher_depth = int(float(safe_str(existing_evaluation["교사_감상의깊이"]) or ai_depth or 10))
                    teacher_count = automatic_count_score
                    teacher_feedback = safe_str(existing_evaluation["교사_피드백"])
                except Exception:
                    pass

            if st.button("✨ AI 자동 채점 실행", use_container_width=True, type="primary"):
                if student_logs.empty:
                    st.error("학생의 독서 기록이 없습니다.")
                else:
                    records = student_logs.fillna("").to_dict("records")
                    with st.spinner("AI가 학생의 누적 독서 포트폴리오를 분석하고 있습니다..."):
                        try:
                            ai_result = run_ai_evaluation(
                                student_name,
                                records,
                                active_rubric
                            )

                            ai_understanding = int(ai_result["understanding"])
                            ai_completeness = int(ai_result["completeness"])
                            ai_depth = int(ai_result["depth"])

                            ai_total = (
                                ai_understanding
                                + ai_completeness
                                + ai_depth
                                + automatic_count_score
                            )

                            ai_reason = ai_result["reason"]
                            ai_feedback = ai_result["feedback"]

                            st.session_state[f"ai_{evaluation_id}_{active_assessment_id}"] = {
                                "understanding": ai_understanding,
                                "completeness": ai_completeness,
                                "depth": ai_depth,
                                "total": ai_total,
                                "reason": ai_reason,
                                "feedback": ai_feedback
                            }

                            st.success("AI 평가가 완료되었습니다.")
                            st.rerun()

                        except Exception as e:
                            st.error(f"AI 평가 중 오류가 발생했습니다: {e}")

            session_ai_key = f"ai_{evaluation_id}_{active_assessment_id}"
            if session_ai_key in st.session_state:
                current_ai = st.session_state[session_ai_key]
                ai_understanding = current_ai["understanding"]
                ai_completeness = current_ai["completeness"]
                ai_depth = current_ai["depth"]
                ai_total = current_ai["total"]
                ai_reason = current_ai["reason"]
                ai_feedback = current_ai["feedback"]

            ai_criteria_rows = []
            for _, rubric_row in active_rubric.iterrows():
                criterion_name = safe_str(rubric_row.get("평가기준"))
                if "작성 횟수" not in criterion_name and "작성횟수" not in criterion_name:
                    ai_criteria_rows.append(rubric_row)

            ai_criteria_rows = ai_criteria_rows[:3]
            score_options_by_criterion = [
                rubric_score_options(row)
                for row in ai_criteria_rows
            ]

            while len(score_options_by_criterion) < 3:
                score_options_by_criterion.append([10])

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
                        f"{ai_understanding} / {max(score_options_by_criterion[0]) if score_options_by_criterion[0] else 0}"
                    )
                    st.metric(
                        "② 작성의 충실도",
                        f"{ai_completeness} / {max(score_options_by_criterion[1]) if score_options_by_criterion[1] else 0}"
                    )

                with a2:
                    st.metric(
                        "③ 감상의 깊이",
                        f"{ai_depth} / {max(score_options_by_criterion[2]) if score_options_by_criterion[2] else 0}"
                    )
                    st.metric(
                        "④ 작성 횟수",
                        f"{automatic_count_score} / 25"
                    )

                with st.expander("🔍 AI 평가 근거 보기", expanded=False):
                    st.write(ai_reason)

                with st.expander("💬 AI 종합 피드백", expanded=True):
                    st.write(ai_feedback)

            else:
                st.warning("아직 AI 평가가 실행되지 않았습니다.")

            st.divider()

            # ====================================================
            # 교사 최종 평가
            # ====================================================

            st.markdown("### ✏️ 교사 최종 평가")
            st.caption("AI 추천 점수를 검토한 뒤 선생님이 최종 점수를 직접 수정할 수 있습니다.")

            def score_button_selector(label, current_value, state_key, score_options):
                if not score_options:
                    score_options = [10]

                if state_key not in st.session_state:
                    st.session_state[state_key] = (
                        current_value if current_value in score_options else score_options[0]
                    )

                st.markdown(f"**{label}**")
                button_cols = st.columns(len(score_options))

                for col, score in zip(button_cols, score_options):
                    with col:
                        is_selected = (st.session_state[state_key] == score)
                        if st.button(
                            f"{'✓ ' if is_selected else ''}{score}점",
                            key=f"{state_key}_{score}",
                            use_container_width=True,
                            type="primary" if is_selected else "secondary"
                        ):
                            st.session_state[state_key] = score

                selected_score = st.session_state[state_key]
                max_score = max(score_options)
                st.caption(f"현재 선택: **{selected_score}점 / {max_score}점**")
                return selected_score

            criterion_labels = [safe_str(row.get("평가기준")) for row in ai_criteria_rows]
            while len(criterion_labels) < 3:
                criterion_labels.append(f"평가기준 {len(criterion_labels)+1}")

            teacher_understanding = score_button_selector(
                f"① {criterion_labels[0]}",
                teacher_understanding,
                f"teacher_understanding_{evaluation_id}_{active_assessment_id}",
                score_options_by_criterion[0]
            )

            teacher_completeness = score_button_selector(
                f"② {criterion_labels[1]}",
                teacher_completeness,
                f"teacher_completeness_{evaluation_id}_{active_assessment_id}",
                score_options_by_criterion[1]
            )

            teacher_depth = score_button_selector(
                f"③ {criterion_labels[2]}",
                teacher_depth,
                f"teacher_depth_{evaluation_id}_{active_assessment_id}",
                score_options_by_criterion[2]
            )

            st.markdown(
                f"""
                **④ 작성 횟수(누락 여부)**

                제출 횟수: **{submission_count}회**

                평가 수준: **{count_level}**

                자동 점수: **{automatic_count_score} / 25점**
                """
            )

            teacher_count = automatic_count_score

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
                        / {sum(max(opts) if opts else 0 for opts in score_options_by_criterion) + (max([int(float(safe_str(get_submission_criterion(active_rubric).get(c)))) for c in ["매우우수점수", "우수점수", "보통점수", "노력요함점수"] if safe_str(get_submission_criterion(active_rubric).get(c))] or [0]))}점
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ----------------------------------------------------
            # 교사 피드백 및 저장 (수정 완료 부분)
            # ----------------------------------------------------

            teacher_feedback = st.text_area(
                "📝 교사 피드백",
                value=teacher_feedback,
                height=160,
                placeholder="학생에게 전달할 교사 종합 피드백 및 총평을 입력하세요."
            )

            if st.button(
                "💾 교사 최종 평가 저장하기",
                use_container_width=True,
                type="primary"
            ):
                try:
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
                        teacher_feedback,
                        active_assessment_id,
                        active_assessment["학년도"],
                        active_assessment["학기"]
                    )

                    st.cache_data.clear()
                    st.success("✅ 교사 최종 평가가 구글 시트에 정상적으로 저장되었습니다!")
                    st.rerun()

                except Exception as e:
                    st.error(f"평가 저장 중 오류가 발생했습니다: {e}")
