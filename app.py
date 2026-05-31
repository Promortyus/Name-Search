from __future__ import annotations

import pandas as pd
import streamlit as st


STEMS = {
    1: ("甲", "木", "阳"),
    2: ("乙", "木", "阴"),
    3: ("丙", "火", "阳"),
    4: ("丁", "火", "阴"),
    5: ("戊", "土", "阳"),
    6: ("己", "土", "阴"),
    7: ("庚", "金", "阳"),
    8: ("辛", "金", "阴"),
    9: ("壬", "水", "阳"),
    0: ("癸", "水", "阴"),
}


def heavenly_stem(value: int) -> str:
    stem, element, yin_yang = STEMS[value % 10]
    return f"{stem}{element} {yin_yang}"


def calculate_name(surname_stroke: int, first_stroke: int, second_stroke: int) -> dict[str, int | str]:
    sky = surname_stroke + 1
    person = surname_stroke + first_stroke
    earth = first_stroke + second_stroke
    total = surname_stroke + first_stroke + second_stroke
    spouse = surname_stroke + second_stroke
    outer = second_stroke + 1

    return {
        "人际关系": outer,
        "夫妻关系": spouse,
        "天格": sky,
        "人格": person,
        "地格": earth,
        "总格": total,
        "人际关系天干": heavenly_stem(outer),
        "夫妻关系天干": heavenly_stem(spouse),
        "天格天干": heavenly_stem(sky),
        "人格天干": heavenly_stem(person),
        "地格天干": heavenly_stem(earth),
        "总格天干": heavenly_stem(total),
    }


def render_sheet_preview(
    surname: str,
    first_name: str,
    second_name: str,
    surname_stroke: int,
    first_stroke: int,
    second_stroke: int,
) -> None:
    result = calculate_name(surname_stroke, first_stroke, second_stroke)
    surname_display = surname or "姓"
    name_1 = first_name or "名一"
    name_2 = second_name or "名二"

    st.markdown(
        f"""
        <div class="sheet">
          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell head">名字</div>
          <div class="cell head">康熙笔画</div>
          <div class="cell head">递进相加</div>
          <div class="cell head">天干</div>
          <div class="cell head">代表</div>

          <div class="cell head">人际关系</div>
          <div class="cell head">夫妻关系</div>
          <div class="cell name">{surname_display}</div>
          <div class="cell num">{surname_stroke}</div>
          <div class="cell result">{result["天格"]}</div>
          <div class="cell">{result["天格天干"]}</div>
          <div class="cell">天格</div>

          <div class="cell result">{result["人际关系"]}</div>
          <div class="cell result">{result["夫妻关系"]}</div>
          <div class="cell name">{name_1}</div>
          <div class="cell num">{first_stroke}</div>
          <div class="cell result">{result["人格"]}</div>
          <div class="cell">{result["人格天干"]}</div>
          <div class="cell">人格</div>

          <div class="cell">{result["人际关系天干"]}</div>
          <div class="cell">{result["夫妻关系天干"]}</div>
          <div class="cell name">{name_2}</div>
          <div class="cell num">{second_stroke}</div>
          <div class="cell result">{result["地格"]}</div>
          <div class="cell">{result["地格天干"]}</div>
          <div class="cell">地格</div>

          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell result">{result["总格"]}</div>
          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell">总格</div>

          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell">{result["总格天干"]}</div>
          <div class="cell"></div>
          <div class="cell"></div>
          <div class="cell"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_results(
    surname_stroke: int,
    first_min: int,
    first_max: int,
    second_min: int,
    second_max: int,
) -> pd.DataFrame:
    rows = []
    for first_stroke in range(first_min, first_max + 1):
        for second_stroke in range(second_min, second_max + 1):
            row = {"名一笔画": first_stroke, "名二笔画": second_stroke}
            row.update(calculate_name(surname_stroke, first_stroke, second_stroke))
            rows.append(row)
    return pd.DataFrame(rows)


def parse_targets(raw_value: str) -> set[int]:
    targets = set()
    for item in raw_value.replace("，", ",").split(","):
        item = item.strip()
        if item:
            targets.add(int(item))
    return targets


def filter_by_targets(df: pd.DataFrame, column: str, raw_value: str) -> pd.DataFrame:
    if not raw_value.strip():
        return df
    targets = parse_targets(raw_value)
    return df[df[column].isin(targets)]


def exclude_by_targets(df: pd.DataFrame, column: str, raw_value: str) -> pd.DataFrame:
    if not raw_value.strip():
        return df
    targets = parse_targets(raw_value)
    return df[~df[column].isin(targets)]


st.set_page_config(page_title="姓名学取名遍历工具", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.5rem; }
      .sheet {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr 1fr 1fr 1fr 1fr;
        border-top: 1px solid #858585;
        border-left: 1px solid #858585;
        overflow-x: auto;
        margin: 0.75rem 0 1.25rem;
      }
      .cell {
        min-height: 44px;
        border-right: 1px solid #858585;
        border-bottom: 1px solid #858585;
        display: flex;
        align-items: center;
        padding: 0 8px;
        font-size: clamp(16px, 2vw, 28px);
        line-height: 1;
        white-space: nowrap;
      }
      .head { font-weight: 600; }
      .name { background: #81c6dc; font-weight: 700; }
      .result { background: #ffc000; justify-content: flex-end; font-variant-numeric: tabular-nums; }
      .num { justify-content: flex-end; font-variant-numeric: tabular-nums; }
      div[data-testid="stDataFrame"] { border: 1px solid #e6e6e6; }
      .filter-section-title {
        margin: 0.25rem 0 0;
        font-size: 0.95rem;
        font-weight: 700;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("姓名学取名遍历工具")

with st.sidebar:
    st.header("输入")
    surname = st.text_input("姓", value="")
    first_name = st.text_input("名一", value="")
    second_name = st.text_input("名二", value="")
    surname_stroke = st.number_input("姓氏康熙笔画", min_value=1, max_value=50, value=17, step=1)
    first_stroke = st.number_input("名一康熙笔画", min_value=1, max_value=50, value=8, step=1)
    second_stroke = st.number_input("名二康熙笔画", min_value=1, max_value=50, value=7, step=1)

    st.header("遍历范围")
    first_range = st.slider("名一笔画范围", 1, 50, (1, 50))
    second_range = st.slider("名二笔画范围", 1, 50, (1, 50))

st.subheader("当前输入预览")
render_sheet_preview(surname, first_name, second_name, surname_stroke, first_stroke, second_stroke)

st.subheader("遍历筛选")
df = build_results(surname_stroke, first_range[0], first_range[1], second_range[0], second_range[1])

st.markdown('<div class="filter-section-title">想要的数字</div>', unsafe_allow_html=True)
filter_cols = st.columns(5, gap="small")
with filter_cols[0]:
    person_targets = st.text_input("人格", placeholder="例如 25", key="person_targets")
with filter_cols[1]:
    earth_targets = st.text_input("地格", placeholder="例如 15, 16", key="earth_targets")
with filter_cols[2]:
    total_targets = st.text_input("总格", placeholder="例如 32", key="total_targets")
with filter_cols[3]:
    sky_targets = st.text_input("天格", placeholder="例如 18, 21", key="sky_targets")
with filter_cols[4]:
    outer_targets = st.text_input("人际", placeholder="例如 8", key="outer_targets")

st.markdown('<div class="filter-section-title">不要的数字</div>', unsafe_allow_html=True)
excluded_number_cols = st.columns(5, gap="small")
with excluded_number_cols[0]:
    excluded_person_numbers = st.text_input("人格", placeholder="例如 24, 25", key="excluded_person_numbers")
with excluded_number_cols[1]:
    excluded_earth_numbers = st.text_input("地格", placeholder="例如 15, 16", key="excluded_earth_numbers")
with excluded_number_cols[2]:
    excluded_total_numbers = st.text_input("总格", placeholder="例如 32", key="excluded_total_numbers")
with excluded_number_cols[3]:
    excluded_spouse_numbers = st.text_input("夫妻", placeholder="例如 24", key="excluded_spouse_numbers")
with excluded_number_cols[4]:
    excluded_outer_numbers = st.text_input("人际", placeholder="例如 8", key="excluded_outer_numbers")

filtered = df.copy()
for col, raw in [
    ("天格", sky_targets),
    ("人格", person_targets),
    ("地格", earth_targets),
    ("总格", total_targets),
    ("人际关系", outer_targets),
]:
    try:
        filtered = filter_by_targets(filtered, col, raw)
    except ValueError:
        st.error(f"{col}目标只能输入数字，用逗号分隔。")
        st.stop()

for col, raw in [
    ("人格", excluded_person_numbers),
    ("地格", excluded_earth_numbers),
    ("总格", excluded_total_numbers),
    ("夫妻关系", excluded_spouse_numbers),
    ("人际关系", excluded_outer_numbers),
]:
    try:
        filtered = exclude_by_targets(filtered, col, raw)
    except ValueError:
        st.error(f"{col}不要的数字只能输入数字，用逗号分隔。")
        st.stop()

all_stem_columns = [
    "人际关系天干",
    "夫妻关系天干",
    "天格天干",
    "人格天干",
    "地格天干",
    "总格天干",
]
all_stem_options = sorted(pd.unique(df[all_stem_columns].to_numpy().ravel()))
st.markdown('<div class="filter-section-title">不要的属性</div>', unsafe_allow_html=True)
exclude_cols = st.columns(5, gap="small")
with exclude_cols[0]:
    excluded_person_stems = st.multiselect("人格", all_stem_options, key="excluded_person_stems")
with exclude_cols[1]:
    excluded_earth_stems = st.multiselect("地格", all_stem_options, key="excluded_earth_stems")
with exclude_cols[2]:
    excluded_total_stems = st.multiselect("总格", all_stem_options, key="excluded_total_stems")
with exclude_cols[3]:
    excluded_spouse_stems = st.multiselect("夫妻", all_stem_options, key="excluded_spouse_stems")
with exclude_cols[4]:
    excluded_outer_stems = st.multiselect("人际", all_stem_options, key="excluded_outer_stems")

for col, excluded in [
    ("人格天干", excluded_person_stems),
    ("地格天干", excluded_earth_stems),
    ("总格天干", excluded_total_stems),
    ("夫妻关系天干", excluded_spouse_stems),
    ("人际关系天干", excluded_outer_stems),
]:
    if excluded:
        filtered = filtered[~filtered[col].isin(excluded)]

display_columns = [
    "名一笔画",
    "名二笔画",
    "人际关系",
    "人际关系天干",
    "夫妻关系",
    "夫妻关系天干",
    "天格",
    "天格天干",
    "人格",
    "人格天干",
    "地格",
    "地格天干",
    "总格",
    "总格天干",
]

st.caption(f"找到 {len(filtered)} 组组合")
st.dataframe(filtered[display_columns], width="stretch", hide_index=True)

st.download_button(
    "下载筛选结果 CSV",
    data=filtered[display_columns].to_csv(index=False).encode("utf-8-sig"),
    file_name="name_search_results.csv",
    mime="text/csv",
)
