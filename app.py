from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
import requests
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
MAX_AGENT_COMBOS = 8
MAX_MEIMINGTENG_VERIFY_CHARS = 48
CODEX_AGENT_MODEL = os.environ.get("NAME_SEARCH_CODEX_MODEL", "gpt-5.5")
OPENAI_API_MODEL = os.environ.get("NAME_SEARCH_OPENAI_MODEL", "gpt-5")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
CHARACTER_DB_PATH = APP_DIR / "characters.csv"
MEIMINGTENG_ZIDIAN_URL = "https://m.meimingteng.com/m/zidian.aspx?zi="
GOOGLE_SHEET_ID = os.environ.get("NAME_SEARCH_GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
    "NAME_SEARCH_GOOGLE_SERVICE_ACCOUNT_FILE",
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
)
GOOGLE_CHARACTERS_WORKSHEET = os.environ.get("NAME_SEARCH_GOOGLE_CHARACTERS_WORKSHEET", "characters")
GOOGLE_LOG_WORKSHEET = os.environ.get("NAME_SEARCH_GOOGLE_LOG_WORKSHEET", "verification_log")
CHARACTER_COLUMNS = ["char", "name_strokes", "wuxing", "pinyin", "source", "verify_count", "last_verified_at", "status"]
VERIFICATION_LOG_COLUMNS = ["char", "name_strokes", "wuxing", "pinyin", "source", "source_url", "verified_at", "result", "error"]


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


def google_sheets_configured() -> bool:
    return bool(GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE)


def normalize_character_db(df: pd.DataFrame) -> pd.DataFrame:
    for col in CHARACTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[CHARACTER_COLUMNS].copy()
    df["char"] = df["char"].astype(str)
    df["name_strokes"] = pd.to_numeric(df["name_strokes"], errors="coerce").astype("Int64")
    df["verify_count"] = pd.to_numeric(df["verify_count"], errors="coerce").fillna(0).astype(int)
    return df


def load_local_character_db() -> pd.DataFrame:
    if not CHARACTER_DB_PATH.exists():
        return normalize_character_db(pd.DataFrame(columns=CHARACTER_COLUMNS))

    return normalize_character_db(pd.read_csv(CHARACTER_DB_PATH))


def get_google_spreadsheet():
    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("未安装 Google Sheets 依赖，请先运行 `pip install -r requirements.txt`。") from exc

    client = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_FILE)
    return client.open_by_key(GOOGLE_SHEET_ID)


def get_or_create_worksheet(spreadsheet, title: str, columns: list[str]):
    from gspread.exceptions import WorksheetNotFound

    try:
        worksheet = spreadsheet.worksheet(title)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(len(columns), 8))
        worksheet.append_row(columns)
        return worksheet

    rows = worksheet.get_all_values()
    if not rows:
        worksheet.append_row(columns)
    return worksheet


def load_google_character_db() -> pd.DataFrame:
    spreadsheet = get_google_spreadsheet()
    worksheet = get_or_create_worksheet(spreadsheet, GOOGLE_CHARACTERS_WORKSHEET, CHARACTER_COLUMNS)
    rows = worksheet.get_all_records()
    return normalize_character_db(pd.DataFrame(rows))


@st.cache_data(ttl=60)
def load_character_db_with_status() -> tuple[pd.DataFrame, dict[str, object]]:
    if google_sheets_configured():
        try:
            return load_google_character_db(), {
                "backend": "google_sheets",
                "ok": True,
                "message": "Google Sheets 字库已连接",
            }
        except Exception as exc:  # noqa: BLE001 - keep app usable if cloud sync fails.
            return load_local_character_db(), {
                "backend": "local_csv",
                "ok": False,
                "message": f"Google Sheets 字库连接失败，已回落本地字库：{exc}",
            }

    return load_local_character_db(), {
        "backend": "local_csv",
        "ok": True,
        "message": "本地 CSV 字库",
    }


def load_character_db() -> pd.DataFrame:
    character_db, _status = load_character_db_with_status()
    return character_db


def character_lookup(character_db: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in character_db.to_dict(orient="records"):
        char = str(row.get("char", "")).strip()
        if char:
            lookup[char] = row
    return lookup


def collect_candidate_chars(candidates: list[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    chars: list[str] = []
    for candidate in candidates:
        for key in ("first_char", "second_char"):
            char = str(candidate.get(key, "")).strip()
            if char and char not in seen:
                seen.add(char)
                chars.append(char)
    return chars


def strip_html_tags(value: str) -> str:
    value = re.sub(r"<script.*?</script>", "", value, flags=re.S | re.I)
    value = re.sub(r"<style.*?</style>", "", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_meimingteng_page(chars: str, timeout: int = 15) -> str:
    request = Request(
        MEIMINGTENG_ZIDIAN_URL + quote(chars),
        headers={
            "User-Agent": "Mozilla/5.0 name-search-local-harness/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_meimingteng_char(page_html: str, char: str) -> dict[str, object]:
    compact = strip_html_tags(page_html)
    match = re.search(re.escape(char) + r".{0,220}?(\d{1,2})\|(\d{1,2}).{0,120}", compact)
    if not match:
        return {
            "char": char,
            "name_strokes": None,
            "wuxing": None,
            "pinyin": None,
            "verified": False,
            "source": "meimingteng",
            "source_url": MEIMINGTENG_ZIDIAN_URL + quote(char),
        }

    window = match.group(0)
    wuxing_match = re.search(r"[金木水火土]", window)
    pinyin_match = re.search(r"\b[a-züv:]{1,12}\b", window, flags=re.I)
    return {
        "char": char,
        "name_strokes": int(match.group(2)),
        "wuxing": wuxing_match.group(0) if wuxing_match else "",
        "pinyin": pinyin_match.group(0) if pinyin_match else "",
        "verified": True,
        "source": "meimingteng",
        "source_url": MEIMINGTENG_ZIDIAN_URL + quote(char),
    }


def verify_meimingteng_chars(chars: list[str], batch_size: int = 4, delay: float = 0.8) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    limited_chars = chars[:MAX_MEIMINGTENG_VERIFY_CHARS]
    for start in range(0, len(limited_chars), batch_size):
        batch = limited_chars[start : start + batch_size]
        try:
            page_html = fetch_meimingteng_page("".join(batch))
            results.extend(parse_meimingteng_char(page_html, char) for char in batch)
        except Exception as exc:  # noqa: BLE001 - keep optional verification resilient.
            results.extend(
                {
                    "char": char,
                    "name_strokes": None,
                    "wuxing": None,
                    "pinyin": None,
                    "verified": False,
                    "source": "meimingteng",
                    "source_url": MEIMINGTENG_ZIDIAN_URL + quote(char),
                    "error": str(exc),
                }
                for char in batch
            )
        if start + batch_size < len(limited_chars):
            time.sleep(delay)
    return results


def stroke_matches(value: object, target: int | None) -> bool:
    if value is None or target is None or pd.isna(value):
        return False
    return int(value) == target


def display_stroke(value: object) -> int | str:
    if value is None or pd.isna(value):
        return ""
    return int(value)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_sources(existing_source: object, new_source: object) -> str:
    sources = []
    for raw in [existing_source, new_source]:
        for item in str(raw or "").replace("，", ",").replace(";", ",").split(","):
            source = item.strip()
            if source and source not in sources:
                sources.append(source)
    return ";".join(sources)


def safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def append_google_verification_logs(worksheet, rows: list[dict[str, object]], result_overrides: dict[str, str]) -> None:
    now = utc_now_iso()
    log_rows = []
    for row in rows:
        char = str(row.get("char", "")).strip()
        if not char:
            continue
        result = result_overrides.get(char) or ("verified" if row.get("verified") else "failed")
        log_rows.append(
            [
                char,
                row.get("name_strokes", "") or "",
                row.get("wuxing", "") or "",
                row.get("pinyin", "") or "",
                row.get("source", "") or "",
                row.get("source_url", "") or "",
                now,
                result,
                row.get("error", "") or "",
            ]
        )
    if log_rows:
        worksheet.append_rows(log_rows, value_input_option="USER_ENTERED")


def upsert_google_verified_characters(rows: list[dict[str, object]]) -> int:
    spreadsheet = get_google_spreadsheet()
    characters_sheet = get_or_create_worksheet(spreadsheet, GOOGLE_CHARACTERS_WORKSHEET, CHARACTER_COLUMNS)
    log_sheet = get_or_create_worksheet(spreadsheet, GOOGLE_LOG_WORKSHEET, VERIFICATION_LOG_COLUMNS)

    existing_rows = characters_sheet.get_all_records()
    existing_by_char = {str(row.get("char", "")).strip(): (idx + 2, row) for idx, row in enumerate(existing_rows)}
    changed = 0
    result_overrides: dict[str, str] = {}
    now = utc_now_iso()

    for row in rows:
        char = str(row.get("char", "")).strip()
        if not char or not row.get("verified") or row.get("name_strokes") is None:
            continue

        new_strokes = safe_int(row.get("name_strokes"))
        new_source = row.get("source", "") or "meimingteng"
        if char in existing_by_char:
            row_number, existing = existing_by_char[char]
            existing_strokes = safe_int(existing.get("name_strokes"), default=-1)
            verify_count = safe_int(existing.get("verify_count")) + 1

            if existing_strokes == -1 or str(existing.get("name_strokes", "")).strip() == "":
                updated = [
                    char,
                    new_strokes,
                    row.get("wuxing", "") or existing.get("wuxing", "") or "",
                    row.get("pinyin", "") or existing.get("pinyin", "") or "",
                    merge_sources(existing.get("source", ""), new_source),
                    verify_count,
                    now,
                    "verified",
                ]
                result_overrides[char] = "verified"
            elif existing_strokes == new_strokes:
                updated = [
                    char,
                    existing_strokes,
                    existing.get("wuxing", "") or row.get("wuxing", "") or "",
                    existing.get("pinyin", "") or row.get("pinyin", "") or "",
                    merge_sources(existing.get("source", ""), new_source),
                    verify_count,
                    now,
                    existing.get("status", "") or "verified",
                ]
                result_overrides[char] = "duplicate_verified"
            else:
                updated = [
                    char,
                    existing.get("name_strokes", ""),
                    existing.get("wuxing", ""),
                    existing.get("pinyin", ""),
                    merge_sources(existing.get("source", ""), new_source),
                    verify_count,
                    now,
                    "conflict",
                ]
                result_overrides[char] = "conflict"

            characters_sheet.update(f"A{row_number}:H{row_number}", [updated], value_input_option="USER_ENTERED")
            changed += 1
        else:
            new_row = [
                char,
                new_strokes,
                row.get("wuxing", "") or "",
                row.get("pinyin", "") or "",
                new_source,
                1,
                now,
                "verified",
            ]
            characters_sheet.append_row(new_row, value_input_option="USER_ENTERED")
            existing_by_char[char] = (len(existing_by_char) + 2, dict(zip(CHARACTER_COLUMNS, new_row)))
            result_overrides[char] = "inserted"
            changed += 1

    append_google_verification_logs(log_sheet, rows, result_overrides)
    if changed:
        load_character_db_with_status.clear()
    return changed


def upsert_local_verified_characters(rows: list[dict[str, object]]) -> int:
    expected_columns = CHARACTER_COLUMNS
    if CHARACTER_DB_PATH.exists():
        character_db = pd.read_csv(CHARACTER_DB_PATH)
    else:
        character_db = pd.DataFrame(columns=expected_columns)

    for col in expected_columns:
        if col not in character_db.columns:
            character_db[col] = ""

    character_db = character_db[expected_columns].copy()
    changed = 0
    existing_chars = {str(char): idx for idx, char in character_db["char"].astype(str).items()}

    for row in rows:
        if not row.get("verified") or row.get("name_strokes") is None:
            continue

        new_row = {
            "char": str(row.get("char", "")).strip(),
            "name_strokes": row.get("name_strokes", ""),
            "wuxing": row.get("wuxing", "") or "",
            "pinyin": row.get("pinyin", "") or "",
            "source": row.get("source", "") or "meimingteng",
            "verify_count": 1,
            "last_verified_at": utc_now_iso(),
            "status": "verified",
        }
        if not new_row["char"]:
            continue

        if new_row["char"] in existing_chars:
            idx = existing_chars[new_row["char"]]
            for col, value in new_row.items():
                current_value = character_db.at[idx, col]
                if pd.isna(current_value) or str(current_value).strip() == "":
                    character_db.at[idx, col] = value
                    changed += 1
            existing_strokes = safe_int(character_db.at[idx, "name_strokes"], default=-1)
            new_strokes = safe_int(new_row["name_strokes"], default=-1)
            if existing_strokes == new_strokes:
                character_db.at[idx, "verify_count"] = safe_int(character_db.at[idx, "verify_count"]) + 1
                character_db.at[idx, "last_verified_at"] = utc_now_iso()
                character_db.at[idx, "source"] = merge_sources(character_db.at[idx, "source"], new_row["source"])
                character_db.at[idx, "status"] = character_db.at[idx, "status"] or "verified"
                changed += 1
            elif existing_strokes != -1 and new_strokes != -1:
                character_db.at[idx, "status"] = "conflict"
                character_db.at[idx, "last_verified_at"] = utc_now_iso()
                changed += 1
        else:
            character_db.loc[len(character_db)] = new_row
            existing_chars[new_row["char"]] = len(character_db) - 1
            changed += 1

    if changed:
        normalize_character_db(character_db).to_csv(CHARACTER_DB_PATH, index=False, encoding="utf-8")
        load_character_db_with_status.clear()
    return changed


def upsert_verified_characters(rows: list[dict[str, object]]) -> tuple[int, str]:
    if google_sheets_configured():
        try:
            return upsert_google_verified_characters(rows), "google_sheets"
        except Exception:
            return upsert_local_verified_characters(rows), "local_csv"

    return upsert_local_verified_characters(rows), "local_csv"


def extract_json_payload(raw_text: str) -> object:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = min([idx for idx in [text.find("["), text.find("{")] if idx >= 0], default=-1)
    end = max(text.rfind("]"), text.rfind("}"))
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("模型没有返回可解析的 JSON。")


def normalize_candidate_payload(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        candidates = payload.get("candidates", [])
    else:
        candidates = payload

    if not isinstance(candidates, list):
        raise ValueError("JSON 中缺少 candidates 列表。")

    normalized = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        first_char = str(item.get("first_char", "")).strip()
        second_char = str(item.get("second_char", "")).strip()
        if not first_char or not second_char:
            name = str(item.get("name", "")).strip()
            if len(name) >= 2:
                first_char = first_char or name[0]
                second_char = second_char or name[1]
        if not first_char or not second_char:
            continue

        normalized.append(
            {
                "combo": str(item.get("combo", "")).strip(),
                "first_char": first_char[0],
                "second_char": second_char[0],
                "name": str(item.get("name", first_char[0] + second_char[0])).strip() or first_char[0] + second_char[0],
                "candidate_source": str(item.get("candidate_source", item.get("source", ""))).strip(),
                "wuxing_pinyin": str(item.get("wuxing_pinyin", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
                "notes": str(item.get("notes", "")).strip(),
            }
        )
    return normalized


def verify_candidate_names(
    candidates: list[dict[str, object]],
    selected_rows: pd.DataFrame,
    surname: str,
    character_db: pd.DataFrame,
) -> pd.DataFrame:
    lookup = character_lookup(character_db)
    combo_targets = {
        f'{int(row["名一笔画"])}-{int(row["名二笔画"])}': (int(row["名一笔画"]), int(row["名二笔画"]))
        for row in selected_rows.to_dict(orient="records")
    }

    rows = []
    for candidate in candidates:
        combo = str(candidate.get("combo", "")).strip()
        if combo not in combo_targets:
            first_target = second_target = None
            if combo_targets:
                combo, (first_target, second_target) = next(iter(combo_targets.items()))
        else:
            first_target, second_target = combo_targets[combo]

        first_char = str(candidate["first_char"])
        second_char = str(candidate["second_char"])
        first_info = lookup.get(first_char)
        second_info = lookup.get(second_char)

        first_strokes = first_info.get("name_strokes") if first_info else None
        second_strokes = second_info.get("name_strokes") if second_info else None
        first_ok = stroke_matches(first_strokes, first_target)
        second_ok = stroke_matches(second_strokes, second_target)

        rows.append(
            {
                "组合": combo,
                "候选名字": f"{surname}{first_char}{second_char}" if surname else first_char + second_char,
                "名一校验": "通过" if first_ok else ("不符" if first_info else "未收录"),
                "名二校验": "通过" if second_ok else ("不符" if second_info else "未收录"),
                "名一笔画": display_stroke(first_strokes),
                "名二笔画": display_stroke(second_strokes),
                "候选来源": candidate.get("candidate_source", ""),
                "名一字库来源": first_info.get("source", "") if first_info else "",
                "名二字库来源": second_info.get("source", "") if second_info else "",
                "五行/读音": candidate.get("wuxing_pinyin", ""),
                "推荐理由": candidate.get("reason", ""),
                "注意事项": candidate.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def get_codex_status() -> dict[str, str | bool]:
    codex_path = shutil.which("codex")
    if not codex_path:
        return {
            "ready": False,
            "message": "当前运行环境未安装本机 Agent（codex CLI）。云端部署无法使用你电脑上的 ChatGPT 登录。",
            "path": "",
            "reason": "missing_command",
        }

    try:
        result = subprocess.run(
            [codex_path, "login", "status"],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - surface local setup failures in the UI.
        return {"ready": False, "message": f"无法检查本机 Agent 登录状态：{exc}", "path": codex_path, "reason": "status_failed"}

    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0 and "Logged in" in output:
        return {"ready": True, "message": output, "path": codex_path}

    return {
        "ready": False,
        "message": output or "本机 Agent 未登录。",
        "path": codex_path,
        "reason": "not_logged_in",
    }


def build_selection_prompt(selected_rows: pd.DataFrame, preferences: str, surname: str) -> str:
    combo_records = selected_rows[
        [
            "名一笔画",
            "名二笔画",
            "人格",
            "地格",
            "总格",
            "夫妻关系",
            "人际关系",
            "人格天干",
            "地格天干",
            "总格天干",
            "夫妻关系天干",
            "人际关系天干",
        ]
    ].to_dict(orient="records")

    return textwrap.dedent(
        f"""
        You are the character-selection model in a local Chinese naming workflow.

        Context:
        - This is a local personal naming helper.
        - The web app has already calculated and filtered name-study stroke combinations.
        - Your job is to gather stroke-matched candidate characters, then propose elegant Chinese given-name candidates.
        - A deterministic local Python verifier will check name-study/Kangxi stroke counts after your response.
        - Do not modify files.
        - Use live web search when available.
        - First try to find candidate characters by target stroke count from kangxizidian.com/kxbihua or page-specific Kangxi stroke URLs.
        - Useful public Kangxi stroke indexes include https://www.kangxizidian.com.cn/bihua/{{stroke}}.html, https://www.kangxizidian.cn/bihua/, https://www.kangxizidian.org/bihua/index.html, and https://www.kangxizidian.net.cn/kangxi/bihua-{{stroke}}.html.
        - Only query the selected stroke counts. Do not bulk crawl a full dictionary.
        - Treat the public Kangxi pages as a candidate pool, not final verification.
        - Exclude characters that are obviously unsuitable for naming: strongly negative meanings, illness/death/violence, vulgar use, extreme obscurity, hard registration risk, or awkward modern usage.
        - Prefer entries marked as auspicious/common/name-appropriate when the source page provides such labels.
        - Prefer modern, name-appropriate Chinese characters.
        - Avoid obscure, hard-to-write, strongly negative, or legally awkward characters unless requested.
        - Respect the user's preferences.

        Surname:
        {surname or "未填写"}

        Selected stroke combinations as JSON:
        {json.dumps(combo_records, ensure_ascii=False, indent=2)}

        User naming preferences:
        \"\"\"
        {preferences.strip() or "无特别偏好。"}
        \"\"\"

        Task:
        Return ONLY valid JSON. Do not wrap it in markdown.
        Shape:
        {{
          "candidates": [
            {{
              "combo": "名一笔画-名二笔画",
              "first_char": "单个汉字",
              "second_char": "单个汉字",
              "name": "两个字名",
              "candidate_source": "简短说明候选来源，例如 kangxizidian.com.cn/bihua/8.html + /7.html；不确定则写未确认",
              "wuxing_pinyin": "简要五行/读音倾向；不确定可留空",
              "reason": "简短推荐理由",
              "notes": "简短注意事项；没有则留空"
            }}
          ]
        }}
        Return 20-40 candidates total. Include multiple candidates for each selected combo.
        """
    ).strip()


def summarize_codex_error(output: str, error: str) -> str:
    raw = "\n\n".join(part for part in [output, error] if part).strip()
    if not raw:
        return "选字模型返回失败。"

    if "requires a newer version of Codex" in raw:
        return (
            f"当前 Codex CLI 不支持模型 `{CODEX_AGENT_MODEL}`，需要升级 Codex 后才能使用。"
            "可以先把环境变量 `NAME_SEARCH_CODEX_MODEL` 设为当前 CLI 支持的模型，再重启 Streamlit。"
        )

    if "not supported when using Codex with a ChatGPT account" in raw:
        return (
            f"当前 ChatGPT 登录方式不支持模型 `{CODEX_AGENT_MODEL}`。"
            "请换成你的账号可用的 Codex 模型，或升级 Codex 后重试。"
        )

    if "tls handshake eof" in raw or "failed to connect to websocket" in raw:
        return (
            "Codex 连接 ChatGPT 服务时 TLS/WebSocket 握手失败。"
            "这通常和当前网络、VPN、代理、防火墙或证书环境有关；CLI 会尝试 HTTPS fallback，"
            "但这次没有成功完成请求。"
        )

    error_lines = [line for line in raw.splitlines() if "ERROR" in line or "error" in line.lower()]
    if error_lines:
        return "\n".join(error_lines[-8:])

    return "\n".join(raw.splitlines()[-20:])


def extract_openai_response_text(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def call_openai_responses_api(
    prompt: str,
    api_key: str,
    model: str,
    use_web_search: bool = True,
    timeout_seconds: int = 180,
) -> tuple[bool, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, object] = {
        "model": model,
        "input": prompt,
    }
    if use_web_search:
        body["tools"] = [{"type": "web_search"}]

    try:
        response = requests.post(OPENAI_RESPONSES_URL, headers=headers, json=body, timeout=timeout_seconds)
    except requests.RequestException as exc:
        return False, f"OpenAI API 调用失败：{exc}"

    if response.status_code >= 400:
        try:
            error_payload = response.json()
            detail = error_payload.get("error", {}).get("message") or error_payload.get("detail") or response.text
        except ValueError:
            detail = response.text

        if use_web_search and response.status_code in {400, 404}:
            fallback_ok, fallback_output = call_openai_responses_api(
                prompt,
                api_key,
                model,
                use_web_search=False,
                timeout_seconds=timeout_seconds,
            )
            if fallback_ok:
                return True, fallback_output

        return False, f"OpenAI API 返回错误：{detail}"

    try:
        payload = response.json()
    except ValueError:
        return False, "OpenAI API 返回了无法解析的结果。"

    text = extract_openai_response_text(payload)
    if not text:
        return False, "OpenAI API 没有返回候选内容。"
    return True, text


def run_codex_selection(prompt: str, timeout_seconds: int = 240) -> tuple[bool, str]:
    status = get_codex_status()
    codex_path = str(status.get("path") or "")
    if not codex_path:
        return False, "未检测到 codex 命令。"

    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="name-search-codex-", suffix=".txt", delete=False) as output_file:
            output_path = Path(output_file.name)

        result = subprocess.run(
            [
                codex_path,
                "--search",
                "exec",
                "-m",
                CODEX_AGENT_MODEL,
                "-C",
                str(APP_DIR),
                "--ephemeral",
                "--ignore-user-config",
                "-s",
                "read-only",
                "--color",
                "never",
                "-o",
                str(output_path),
                "-",
            ],
            input=prompt,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"选字模型运行超过 {timeout_seconds} 秒，已停止。"
    except Exception as exc:  # noqa: BLE001 - surface local execution failures.
        return False, f"选字模型调用失败：{exc}"
    finally:
        last_message = ""
        if output_path and output_path.exists():
            last_message = output_path.read_text(encoding="utf-8", errors="replace").strip()
            output_path.unlink(missing_ok=True)

    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        return False, summarize_codex_error(output, error)

    return True, last_message or output or error or "选字模型没有返回内容。"


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

    st.header("AI 生成")
    openai_api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value="",
        help="仅用于当前会话生成候选，不会写入本地文件或字库。",
    )
    openai_api_model = st.text_input("API 模型", value=OPENAI_API_MODEL)
    st.caption("部署版没有本机 Agent 时，可用 API Key 启用候选生成。")

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
display_df = filtered[display_columns].copy()
selection_df = display_df.copy()
selection_df.insert(0, "选择", False)
edited_selection = st.data_editor(
    selection_df,
    width="stretch",
    hide_index=True,
    disabled=display_columns,
    column_config={
        "选择": st.column_config.CheckboxColumn("选择", help="勾选后可交给本机 Agent 生成候选汉字。")
    },
)

st.download_button(
    "下载筛选结果 CSV",
    data=display_df.to_csv(index=False).encode("utf-8-sig"),
    file_name="name_search_results.csv",
    mime="text/csv",
)

st.subheader("AI 候选汉字")
character_db, character_db_status = load_character_db_with_status()
codex_status = get_codex_status()
api_key_ready = bool(openai_api_key.strip())
generation_mode = "codex" if codex_status["ready"] else ("openai_api" if api_key_ready else "disabled")

if generation_mode == "codex":
    st.success("已检测到本机 ChatGPT 登录，可使用本地 Agent 生成候选名字")
    st.caption(f"当前选字模型：{CODEX_AGENT_MODEL}")
elif generation_mode == "openai_api":
    st.success("已检测到 OpenAI API Key，可使用云端 API 生成候选名字")
    st.caption(f"当前选字模型：{openai_api_model.strip() or OPENAI_API_MODEL}")
else:
    st.warning(f"候选生成功能未启用：{codex_status['message']}")
    if codex_status.get("reason") == "missing_command":
        st.caption("部署版仍可使用笔画筛选和字库校验；如需生成候选，请在左侧栏输入 OpenAI API Key。")
    else:
        st.caption("请在运行这个 Streamlit 服务的机器上执行 `codex login`，然后刷新页面。")

if not character_db_status["ok"]:
    st.warning(str(character_db_status["message"]))

if character_db.empty:
    st.warning("未找到可用字库，生成结果只能标为未校验。")
elif character_db_status["backend"] == "google_sheets":
    st.caption(f"云端字库已加载 {len(character_db)} 个字；已完成姓名学笔画验证")
else:
    st.caption(f"本地字库已加载 {len(character_db)} 个字；已完成姓名学笔画验证")

selected_rows = edited_selection[edited_selection["选择"]].drop(columns=["选择"])
preferences = st.text_area(
    "名字偏好",
    placeholder="例如：女孩名，清雅温柔；避免生僻字；希望带木/水意象；读音不要拗口；不要网红感。",
    height=110,
)

selected_count = len(selected_rows)
st.caption(f"已选择 {selected_count} 个笔画组合，最多建议一次选择 {MAX_AGENT_COMBOS} 个。")

generate_disabled = generation_mode == "disabled" or selected_count == 0 or selected_count > MAX_AGENT_COMBOS
if selected_count > MAX_AGENT_COMBOS:
    st.error(f"一次选择太多会让校验变慢。请先缩到 {MAX_AGENT_COMBOS} 个组合以内。")

if st.button("生成候选", disabled=generate_disabled):
    spinner_text = "Agent 正在按康熙笔画找候选字，随后小批量查美名腾并用本地代码校验..."
    if generation_mode == "openai_api":
        spinner_text = "OpenAI API 正在按康熙笔画找候选字，随后小批量查美名腾并用本地代码校验..."
    with st.spinner(spinner_text):
        prompt = build_selection_prompt(selected_rows, preferences, surname)
        if generation_mode == "openai_api":
            ok, agent_output = call_openai_responses_api(
                prompt,
                openai_api_key.strip(),
                openai_api_model.strip() or OPENAI_API_MODEL,
            )
        else:
            ok, agent_output = run_codex_selection(prompt)
    if ok:
        try:
            with st.spinner("正在小批量查询美名腾并补充本地字库..."):
                payload = extract_json_payload(agent_output)
                candidates = normalize_candidate_payload(payload)
                candidate_chars = collect_candidate_chars(candidates)
                known_chars = set(character_db["char"].astype(str)) if not character_db.empty else set()
                unknown_chars = [char for char in candidate_chars if char not in known_chars]
                meimingteng_results = verify_meimingteng_chars(unknown_chars) if unknown_chars else []
                upsert_count, storage_backend = upsert_verified_characters(meimingteng_results)
                if upsert_count:
                    character_db, character_db_status = load_character_db_with_status()
                verified_df = verify_candidate_names(candidates, selected_rows, surname, character_db)
        except Exception as exc:  # noqa: BLE001 - show parse/verification failures in the UI.
            st.error(f"模型输出解析失败：{exc}")
            st.code(agent_output)
        else:
            verified_count = sum(1 for row in meimingteng_results if row.get("verified"))
            if unknown_chars:
                verification_errors = sorted({str(row.get("error", "")) for row in meimingteng_results if row.get("error")})
                st.caption(
                    f"美名腾小批量验证：尝试 {min(len(unknown_chars), MAX_MEIMINGTENG_VERIFY_CHARS)} 个未知字，"
                    f"确认 {verified_count} 个，写入/补全 {upsert_count} 处"
                    f"{'云端字库' if storage_backend == 'google_sheets' else '本地字库'}字段。"
                )
                if verification_errors:
                    st.caption(f"外部验证失败示例：{verification_errors[0]}。已回落到当前字库结果。")
                if len(unknown_chars) > MAX_MEIMINGTENG_VERIFY_CHARS:
                    st.caption(f"另有 {len(unknown_chars) - MAX_MEIMINGTENG_VERIFY_CHARS} 个未知字本次未查询。")
            st.dataframe(verified_df, width="stretch", hide_index=True)
            st.download_button(
                "下载候选名字 CSV",
                data=verified_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="name_candidates.csv",
                mime="text/csv",
            )
    else:
        st.error(agent_output)
