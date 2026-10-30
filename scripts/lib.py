"""딜 노트·브리핑·사전 파일을 읽는 공용 함수."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

NAME_FIELDS = ["인수자", "대상", "매도자", "재무 자문", "법률 자문"]
LIST_FIELDS = ["지역", "유형", "업종", "테마", "출처"] + NAME_FIELDS
REQUIRED_FIELDS = ["제목", "상태", "신뢰도", "발표일", "최종 업데이트", "지역", "규모 구간",
                   "규모(원화)", "규모(원 통화)", "유형", "업종", "테마"] + NAME_FIELDS + ["출처"]
SECTIONS = ["한 줄 요약", "딜 구조", "밸류에이션", "왜 중요한가", "면접 포인트", "진행 이력", "관련 딜·뉴스"]


def split_front(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("머리말(--- ... ---)이 없음")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("머리말 형식 오류")
    return meta, m.group(2)


def as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def load_tags() -> dict:
    return yaml.safe_load((ROOT / "tags.yml").read_text(encoding="utf-8"))


def load_entities() -> dict:
    data = yaml.safe_load((ROOT / "entities.yml").read_text(encoding="utf-8")) or {}
    return data


def alias_map(entities: dict) -> dict:
    m = {}
    for name, info in entities.items():
        m[name.lower()] = name
        for a in (info or {}).get("aliases", []) or []:
            m[str(a).lower()] = name
    return m


def deal_files() -> list[Path]:
    return sorted((ROOT / "deals").glob("*/*.md"))


def briefing_files() -> list[Path]:
    return sorted((ROOT / "briefings").glob("*.md"))


def load_deal(path: Path) -> tuple[dict, str]:
    meta, body = split_front(path.read_text(encoding="utf-8"))
    for f in LIST_FIELDS:
        meta[f] = [str(x) for x in as_list(meta.get(f))]
    for f in ("발표일", "최종 업데이트"):
        if meta.get(f) is not None:
            meta[f] = str(meta[f])
    return meta, body


def body_names(body: str) -> list[str]:
    return re.findall(r"\[\[([^\]]+)\]\]", body)
