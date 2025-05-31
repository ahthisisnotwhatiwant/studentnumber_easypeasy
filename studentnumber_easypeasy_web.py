import streamlit as st
import json
import pandas as pd
from io import BytesIO
import uuid
import os
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(page_title="예상학생수왕초보만", layout="centered")

# 상수 정의
YIELD_RATE_FILE = "student_yield_rate.json"
HIGH_SCHOOL_YIELD_RATE_FILE = "high_school_yield_rate.json"
VERSION = "v1.1.1(2025. 5. 7.)"  # 버전 상수 추가

# 숫자 포맷팅 함수
def format_number(number):
    """회계 서식으로 정수 포맷팅 (예: 1000 → 1,000)"""
    return f"{int(number):,}"

def format_percentage(number):
    """퍼센트를 소수점 둘째 자리로 포맷팅"""
    return f"{number:.2f}"

# JSON 파일 로드 함수
def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"성공적으로 {path} 파일 로드")
                return data
        else:
            st.warning(f"⚠️ 파일이 없습니다: {path}. 기본값으로 초기화합니다.")
            logger.warning(f"{path} 파일이 존재하지 않음")
            return {}
    except Exception as e:
        st.error(f"❌ 파일 로드 실패: {path}, 에러: {e}")
        logger.error(f"{path} 파일 로드 실패: {e}")
        return {}

# JSON 파일 저장 함수
def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()  # 즉시 디스크에 쓰기
            os.fsync(f.fileno())  # 파일 시스템 동기화
        logger.info(f"성공적으로 {path} 파일 저장")
        # 저장 후 파일 다시 읽어 확인
        with open(path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            if saved_data == data:
                logger.info(f"{path} 파일 저장 확인 완료")
            else:
                logger.error(f"{path} 파일 저장 불일치")
                st.error(f"❌ {path} 파일 저장 불일치")
    except Exception as e:
        st.error(f"❌ 파일 저장 실패: {path}, 에러: {e}")
        logger.error(f"{path} 파일 저장 실패: {e}")

# 세션 상태 초기화
if "rates" not in st.session_state:
    st.session_state.rates = load_json(YIELD_RATE_FILE)
if "high_school_rates" not in st.session_state:
    st.session_state.high_school_rates = load_json(HIGH_SCHOOL_YIELD_RATE_FILE)
if "units_inputted" not in st.session_state:
    st.session_state.units_inputted = 0
if "calculated_results" not in st.session_state:
    st.session_state.calculated_results = []

# 스타일 정의
gradient_text_style = """
<style>
.gradient-text {
    background: linear-gradient(90deg, #ff2d55, #f81788, #c225c2, #7a3de9, #007aff);
    -webkit-background-clip: text;
    color: transparent;
    font-size: 3.5em;
    font-weight: bold;
    text-align: center;
    margin-bottom: 10px;
}
.subheader-gradient-text {
    background: linear-gradient(90deg, #00c6ff, #007bff, #1e3c72);
    -webkit-background-clip: text;
    color: transparent;
    font-size: 1.8em;
    font-weight: bold;
    text-align: center;
    margin-top: -25px;
    margin-bottom: 30px;
}
.tab-header-style {
    font-size: 2.5em !important;
    font-weight: bold;
    color: #333;
    margin-bottom: 15px;
}
.version-text {
    font-size: 0.9em;
    color: #666;
    text-align: center;
    margin-top: -30px;
    margin-bottom: 10px;
}
</style>
"""

# 데이터 접근 유틸리티
def get_node(data, path, default=None):
    node = data
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node

def set_node(data, path, value):
    node = data
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value

# 드롭다운 함수들
def get_cities():
    return sorted(
        list({
            region.split(" ")[0]
            for region in st.session_state.rates.keys()
            if isinstance(st.session_state.rates[region], dict)
        })
    )

def get_regions(city):
    return sorted([r for r in st.session_state.rates.keys() if r.startswith(city)])

def get_types(region):
    return sorted(st.session_state.rates.get(region, {}).keys())

def get_subtypes(region, housing_type):
    return sorted(
        st.session_state.rates.get(region, {}).get(housing_type, {}).keys()
    )

def get_scales(region, housing_type, subtype):
    return sorted(
        st.session_state.rates.get(region, {})
        .get(housing_type, {})
        .get(subtype, {})
        .keys()
    )

# 학생 수 계산
def calculate_student_counts(city, region, housing_type, subtype, scale, units, tab):
    if not all([city, region, housing_type, subtype, scale]):
        tab.error("❌ 모든 항목을 선택해주세요.")
        return
    if units <= 0:
        tab.warning("⚠️ 세대 수는 1 이상이어야 합니다!")
        return

    data = get_node(st.session_state.rates, [region, housing_type, subtype, scale], {})
    if not data:
        tab.warning("⚠️ 해당 조합의 학생 발생률이 설정되지 않았습니다!")
        return

    high_school_data = get_node(st.session_state.high_school_rates, [region, housing_type, subtype, scale], {})
    if not high_school_data:
        tab.warning("⚠️ 해당 조합의 고등-학생 점유율이 설정되지 않았습니다!")
        return

    e_rate = data.get("초등", 0)
    m_rate = data.get("중등", 0)
    high_school_personnel = high_school_data.get("인원", 0)
    high_school_rate = high_school_data.get("발생률", 0)

    e = round(units * e_rate / 100)  # Round to nearest integer
    k = round(e * 0.5)  # Round to nearest integer, kindergarten is 50% of elementary
    m = round(units * m_rate / 100)  # Round to nearest integer
    h = round(units * high_school_personnel * high_school_rate / 100)  # Round to nearest integer
    h_basis = f"세대수 X {format_number(high_school_personnel)}명 X {format_percentage(high_school_rate)}%"

    result_table = f"""
| 주택유형         | 공급유형 | 주택규모 | 세대수 | 유치원생 | 초등학생 | 중학생 | 고등학생 |
| :-------------: | :------: | :------: | :----: | :------: | :------: | :----: | :------: |
| {housing_type} | {subtype} | {scale}  | {format_number(units)} | {format_number(k)}명 | {format_number(e)}명 | {format_number(m)}명 | {format_number(h)}명 |
"""
    tab.success("✅ 예상 학생 수:\n" + result_table)

    calculation_basis = f"""
📝 **예상 학생 수 계산 근거**:
- **유치원생**: 예상 초등학생 수 X 50%
- **초등학생**: 세대수 X 초등학생 발생률 {format_percentage(e_rate)}%({region} 발생률 적용)
- **중학생**: 세대수 X 중학생 발생률 {format_percentage(m_rate)}%({region} 발생률 적용)
- **고등학생**: {h_basis}
"""
    tab.markdown(calculation_basis)

    # 계산 결과 세션에 저장
    if "calculated_results" not in st.session_state:
        st.session_state.calculated_results = []
    st.session_state.calculated_results.append(
        {
            "시": city,
            "지역": region,
            "주택유형": housing_type,
            "공급유형": subtype,
            "주택규모": scale,
            "세대수": units,
            "유치원생": k,
            "초등학생": e,
            "중학생": m,
            "고등학생": h,
        }
    )

# 엑셀 처리
def process_excel(file, tab):
    try:
        df = pd.read_excel(file)
        required_cols = {
            "시",
            "지역",
            "주택유형",
            "공급유형",
            "주택규모",
            "초등",
            "중등",
            "고등-세대당 인구수",
            "고등-학생 점유율",
        }
        if not required_cols.issubset(df.columns):
            tab.error(
                "❌ 엑셀에 필수 열(시, 지역, 주택유형, 공급유형, 주택규모, 초등, 중등, 고등-세대당 인구수, 고등-학생 점유율)이 부족합니다."
            )
            return

        new_rates = {}
        new_high_school_rates = {}
        for _, row in df.iterrows():
            city, r, h, s, sc = (
                str(row["시"]),
                str(row["지역"]),
                str(row["주택유형"]),
                str(row["공급유형"]),
                str(row["주택규모"]),
            )
            full_region = f"{city} {r}"
            e, m = round(float(row["초등"]), 2), round(float(row["중등"]), 2)
            new_rates.setdefault(full_region, {})
            new_rates[full_region].setdefault(h, {})
            new_rates[full_region][h].setdefault(s, {})[sc] = {"초등": e, "중등": m}

            high_school_personnel = row.get("고등-세대당 인구수")
            high_school_rate = row.get("고등-학생 점유율")

            if pd.notna(high_school_personnel) and pd.notna(high_school_rate) and high_school_personnel != "" and high_school_rate != "":
                new_high_school_rates.setdefault(full_region, {})
                new_high_school_rates[full_region].setdefault(h, {})
                new_high_school_rates[full_region][h].setdefault(s, {})[sc] = {
                    "인원": round(float(high_school_personnel), 2),
                    "발생률": round(float(high_school_rate), 2),
                }

        # 수정된 코드 (메모리에만 반영하고 저장 X)
        st.session_state.rates = new_rates
        st.session_state.high_school_rates = new_high_school_rates

        tab.success(f"✅ {format_number(len(df))}개 조합 저장 및 업데이트 완료!")
        logger.info(f"엑셀 파일 처리 완료: {len(df)}개 조합")
    except Exception as e:
        tab.error(f"❌ 엑셀 처리 실패: {e}")
        logger.error(f"엑셀 처리 실패: {e}")

# 엑셀 다운로드 변환
def to_excel(df):
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
            workbook = writer.book
            worksheet = writer.sheets["Sheet1"]
            format1 = workbook.add_format({"num_format": "0.00"})
            cols_to_format = ["초등", "중등", "고등-세대당 인구수", "고등-학생 점유율"]
            for col_num, col_name in enumerate(df.columns):
                if col_name in cols_to_format:
                    column_letter = chr(ord("A") + col_num)
                    worksheet.set_column(f"{column_letter}:{column_letter}", None, format1)
        return output.getvalue()
    except Exception as e:
        st.error(f"❌ 엑셀 파일 생성 실패: {e}")
        logger.error(f"엑셀 파일 생성 실패: {e}")
        return None

# 메인 실행
def main():
    st.markdown(gradient_text_style, unsafe_allow_html=True)
    st.markdown('<div class="gradient-text">예상학생수왕초보만</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subheader-gradient-text">발업 저글링처럼 빠르게 파악! 더이상 GG는 없다</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="version-text">{VERSION}</div>', unsafe_allow_html=True)

    tabs = st.tabs(["📌 앱 안내", "🧮 예상 학생 수", "📊 계산 결과 누적", "⚙️ 학생 발생률 정보 관리"])
    intro_tab, calc_tab, result_tab, rate_tab = tabs

    # 1. 앱 안내 탭
    intro_tab.markdown('<p class="tab-header-style">📌 앱 안내</p>', unsafe_allow_html=True)
    intro_tab.markdown(
        """
        🏹 **기능**
        - 시, 지역, 주택유형 등 조건에 따른 예상 학생 수를 빠르고 간편하게 계산할 수 있습니다.

        💁 **사용 순서 및 방법**
        1.  (처음 사용 시) 4번째 탭 하단에 위치한 '기존 목록 다운로드'를 눌러 다운받아주세요.
        2.  (처음 사용 시) 다운받은 '학생 발생률 목록' 엑셀 파일을 더블클릭하여 열어주세요.
        3.  (처음 사용 시) 학생 발생률 정보를 엑셀 파일 내 서식에 맞추어 작성 후 저장해주세요.
        4.  4번째 탭 중간에 위치한 'Browse files'를 눌러 최신 '학생 발생률 목록' 엑셀 파일을 업로드해주세요.
        5.  2번째 탭으로 이동하여 계산해주세요.

        ⚠️ **주의 및 참고 사항**
        - 앱 종료 후 재실행 시 기존에 업로드한 학생 발생률 목록이 삭제되고 초기 예시로 돌아갑니다.
        - 반드시 작성 후 저장한 최신 '학생 발생률 목록' 엑셀 파일을 삭제하지 말고 보관해주세요.
        - 업로드한 '학생 발생률 목록' 엑셀 파일의 정보는 서버에 남지 않으며 타 이용자가 알 수 없습니다.
        - '학생 발생률 목록' 엑셀 파일의 정보가 외부로 유출되지 않게 유의해주세요.

        📧 **건의 사항 → hanjy3203@korea.kr**
        """
    )

    # 2. 계산 탭
    calc_tab.markdown('<p class="tab-header-style">🧮 예상 학생 수</p>', unsafe_allow_html=True)
    calc_tab.info("①시 ②지역 ③주택유형 ④공급유형 ⑤주택규모 ⑥세대 수 → '계산하기' 클릭 또는 Enter")

    col1, col2 = calc_tab.columns(2)
    city = col1.selectbox("시 선택", get_cities(), key="c_city")
    region = col2.selectbox("지역 선택", get_regions(city), key="c_region", disabled=not city)

    col3, col4 = calc_tab.columns(2)
    housing_type = col3.selectbox(
        "주택유형 선택", get_types(region), key="c_type", disabled=not region
    )
    subtype = col4.selectbox(
        "공급유형 선택",
        get_subtypes(region, housing_type),
        key="c_subtype",
        disabled=not housing_type,
    )

    col5, col6 = calc_tab.columns(2)
    scale = col5.selectbox(
        "주택규모 선택",
        get_scales(region, housing_type, subtype),
        key="c_scale",
        disabled=not subtype,
    )
    units = col6.number_input(
        "세대 수 입력",
        min_value=0,
        step=1,
        key="c_units",
        disabled=not scale,
        on_change=lambda: st.session_state.update(
            units_inputted=st.session_state.c_units
        ),
    )

    calc_tab.markdown("---")

    is_calculation_possible = scale
    if calc_tab.button("👩‍🏫 계산하기", disabled=not is_calculation_possible) or (
        st.session_state.units_inputted != 0
        and st.session_state.units_inputted != st.session_state.get("last_calculated_units", -1)
    ):
        if is_calculation_possible:
            calculate_student_counts(
                city,
                region,
                housing_type,
                subtype,
                scale,
                st.session_state.c_units,
                calc_tab
            )
            st.session_state["last_calculated_units"] = st.session_state.c_units
            st.session_state.units_inputted = 0
        else:
            calc_tab.error("❌ 계산에 필요한 모든 값을 입력해주세요.")

    # 3. 결과 탭
    result_tab.markdown('<p class="tab-header-style">📊 계산 결과 누적</p>', unsafe_allow_html=True)
    if "calculated_results" not in st.session_state or not st.session_state.calculated_results:
        result_tab.info("'🧮 예상 학생 수' 탭에서 계산을 먼저 진행해주세요.")
    else:
        result_tab.info("✅ 계산 결과를 확인하고, 필요한 경우 삭제할 수 있습니다.")
        result_tab.markdown(
            '<div style="text-align: right; font-size: 0.8em;">(단위: 세대, 명)</div>',
            unsafe_allow_html=True,
        )
        result_df = pd.DataFrame(st.session_state.calculated_results)
        result_df = result_df[
            ["시", "지역", "주택유형", "공급유형", "주택규모", "세대수", "유치원생", "초등학생", "중학생", "고등학생"]
        ]
        # Apply formatting to numeric columns
        result_df["세대수"] = result_df["세대수"].apply(format_number)
        result_df["유치원생"] = result_df["유치원생"].apply(format_number)
        result_df["초등학생"] = result_df["초등학생"].apply(format_number)
        result_df["중학생"] = result_df["중학생"].apply(format_number)
        result_df["고등학생"] = result_df["고등학생"].apply(format_number)
        result_tab.dataframe(result_df, use_container_width=True, hide_index=True)

        options = [f"{format_number(i+1)} 번째 줄" for i in range(len(st.session_state.calculated_results))]
        selected_indices = result_tab.multiselect("삭제할 계산 결과 선택", options)
        if result_tab.button("🗑️ 선택한 결과 삭제"):
            original_indices = [int(option.split()[0].replace(",", "")) - 1 for option in selected_indices]
            new_results = [
                result
                for i, result in enumerate(st.session_state.calculated_results)
                if i not in original_indices
            ]
            st.session_state.calculated_results = new_results
            result_tab.success("✅ 선택한 계산 결과를 삭제했습니다.")
            st.rerun()

    # 4. 발생률 탭
    rate_tab.markdown(
        '<p class="tab-header-style">⚙️ 학생 발생률 정보 관리</p>',
        unsafe_allow_html=True,
    )
    rate_tab.info("①기존 목록 다운로드 ②엑셀 내 정보 작성 및 수정 ③엑셀 업로드 → 자동 연동")
    rate_tab.subheader("📤 엑셀 업로드")
    rate_tab.markdown(
        """
        <style>
        div[data-testid="stDownloadButton"] {
            margin-top: -30px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    rate_tab.markdown(
        """
<style>
div[data-testid="stFileUploader"] {
    margin-top: -50px;
}
</style>
""",
        unsafe_allow_html=True,
    )

    excel_file = rate_tab.file_uploader(label="", type=["xlsx"])
    if excel_file:
        with st.spinner("엑셀 파일 처리 중..."):
            process_excel(excel_file, rate_tab)

    rate_tab.subheader("📊 저장된 학생 발생률 정보")
    rate_tab.markdown(
        '<div style="text-align: right; font-size: 0.8em;">(단위: %, %, 명, %)</div>',
        unsafe_allow_html=True,
    )

    rate_data = [
        {
            "시": r.split(" ")[0] if " " in r else r,
            "지역": r.split(" ")[1] if " " in r else r,
            "주택유형": t,
            "공급유형": s,
            "주택규모": sc,
            "초등": format_percentage(v.get("초등", 0.0)),
            "중등": format_percentage(v.get("중등", 0.0)),
            "고등-세대당 인구수": format_percentage(st.session_state.high_school_rates.get(r, {})
                .get(t, {})
                .get(s, {})
                .get(sc, {})
                .get("인원", 0.0))
                if st.session_state.high_school_rates.get(r, {})
                .get(t, {})
                .get(s, {})
                .get(sc, {})
                else "0.00",
            "고등-학생 점유율": format_percentage(st.session_state.high_school_rates.get(r, {})
                .get(t, {})
                .get(s, {})
                .get(sc, {})
                .get("발생률", 0.0))
                if st.session_state.high_school_rates.get(r, {})
                .get(t, {})
                .get(s, {})
                .get(sc, {})
                else "0.00",
        }
        for r, types in st.session_state.rates.items()
        for t, subtypes in types.items()
        for s, scales in subtypes.items()
        for sc, v in scales.items()
    ]
    rate_df = pd.DataFrame(rate_data)
    rate_tab.dataframe(rate_df, use_container_width=True, hide_index=True)
    rate_tab.markdown("<br>", unsafe_allow_html=True)

    excel_data = to_excel(rate_df)
    if excel_data:
        rate_tab.download_button(
            label="💾 기존 목록 다운로드",
            data=excel_data,
            file_name="학생 발생률 목록.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ⭐ 메인 실행
main()
