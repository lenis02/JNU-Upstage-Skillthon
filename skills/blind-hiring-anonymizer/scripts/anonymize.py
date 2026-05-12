#!/usr/bin/env python3
"""블라인드 채용 탐지기: 자기소개서에서 신원 식별 가능한 부분을 찾아 반환합니다."""

import os
import sys
import json
import argparse
from pathlib import Path

# Windows 콘솔의 기본 인코딩(cp949/cp1252)이 한국어를 깨뜨리는 문제 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from openai import OpenAI

env_path = Path(__file__).parent.parent / "assets" / ".env"
load_dotenv(dotenv_path=env_path)

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
if not UPSTAGE_API_KEY:
    print(json.dumps({"error": f"UPSTAGE_API_KEY가 설정되지 않았습니다. {env_path} 파일을 확인하세요."}))
    sys.exit(1)

client = OpenAI(
    api_key=UPSTAGE_API_KEY,
    base_url="https://api.upstage.ai/v1",
)

# ── 공식 블라인드 채용 가이드라인 기반 탐지 기준 ──────────────────────────────

# 어떤 sensitivity에서도 절대 놓치면 안 되는 항목
_MUST_DETECT = """
【최우선 항목 — 반드시 빠짐없이 탐지하세요】
1. 이름·성명 (예: 홍길동, 김○○) → 반드시 탐지
2. 전화번호 (예: 010-0000-0000) → 반드시 탐지
3. 이메일 주소 (예: user@domain.com, @snu.ac.kr 등 학교 도메인 포함) → 반드시 탐지
4. 주민등록번호 → 반드시 탐지
""".strip()

# 공식 가이드라인 카테고리 (직접 언급)
_DIRECT_CATEGORIES = """
【성별 유추 표현】
병역 관련 표현은 남성만 의무 복무하므로 성별이 직접 유추됩니다.
- 병역 복무 형태 직접 언급: 현역, 보급병, 의경, 사회복무요원, 상근예비역 등
- 형제 서열에서 성별이 드러나는 표현: 장남, 차남, 외아들, 장녀, 외동딸 등

【출신지역·본적】
- 시·군·구 이하 수준의 구체적 지역명 (예: 부산 기장군, 광주 북구)
- "줄곧 ○○에서 자라왔으며" 등 성장 지역을 특정하는 표현

【가족관계】
- 직계 존비속·형제자매의 직업·직장 언급 (예: 아버지께서 ○○병원 재직)
- 가족의 학력·재산·병력·종교 언급 (예: 가족 모두 박사학위, 독실한 기독교 신자이신 아버지)
- 간접 언급도 포함 (예: 간호사이신 어머니의 영향으로)

【생년월일·연령】
- 나이·생년월일 직접 언급 (예: 만 28세, 1997년생)
- 간접 연령 유추 표현 (예: "월드컵이 개최되던 해에 태어나", "30대가 되어", "늦은 나이에 지원")

【출신학교】
- 학교명 직접 언급 (대학교·고등학교·중학교·초등학교)
- 학교 약어 (예: SNU, SKY, KU, KAIST 등)
- 학교 이메일 도메인 (예: @jnu.ac.kr, @snu.ac.kr)
- 학교명이 드러나는 단체명·행사명 (예: 전남대 대동제, SNU ○○단체)

【혼인·임신·자녀】
- 혼인 여부 언급 (예: 결혼 후 ~, 미혼으로서)
- 임신·출산·육아 언급 (예: 출산 후 육아로 인한 공백)
- 자녀 관련 언급

【종교·신앙】
- 종교 명칭 직접 언급 (기독교, 천주교, 불교, 이슬람 등)
- 종교시설·활동 언급 (예: 매주 교회에 나가, 성당 봉사)

【신체조건·용모】
- 키·몸무게 수치 직접 언급 (예: 키 185cm, 50kg)
- 외모·체형 묘사
""".strip()

# high 전용 — 더 미묘한 문맥적 단서
_HIGH_CONTEXTUAL = """
【문맥적 식별 정보 — 고감도 추가 탐지】
- 특정 회사·기관명 (근무지·인턴 등으로 신원 식별 가능)
- 특정 건물·장소명 (예: ○○타워, ○○빌딩)
- 실명과 직책을 함께 언급한 제3자 (예: 김○○ 수석연구원)
- 수상 내역 중 수여 기관이 드러나는 경우
- 학교·지역이 드러나는 동아리·조직명
- 검색으로 신원 특정 가능한 프로젝트·논문명
- 외부 프로필 링크 (GitHub, LinkedIn 등)
- 특정 봉사기관명
""".strip()

_SCORE_GUIDE = """
risk_score (0–100 정수, 탐지 항목의 수와 심각도 기반):
- 성명·주민번호·연락처 각 1건 +20
- 출신학교·지역 각 1건 +15
- 성별유추·가족관계·연령유추·혼인·종교·신체조건 각 1건 +10
- 문맥적 식별 정보(high 전용) 각 1건 +8
- 최대 100
""".strip()

_VERIFY_STEP = """
결과를 반환하기 전, 아래 항목이 원문에 존재한다면 risky_entities에 반드시 포함되었는지 확인하세요:
- 사람 이름 (한국 성+이름 패턴) → 있으면 반드시 포함
- 전화번호 패턴 (010-xxxx-xxxx 등) → 있으면 반드시 포함
- 이메일 주소 (@ 포함 문자열) → 있으면 반드시 포함
- 병역 관련 표현 (현역, 사회복무요원 등) → 성별 유추로 반드시 포함
- 형제 서열+성별 표현 (장남, 외동딸 등) → 성별 유추로 반드시 포함
누락이 있으면 추가한 뒤 반환하세요.
""".strip()

SYSTEM_PROMPTS = {
    "low": f"""당신은 블라인드 채용 전문가입니다. 아래 한국 블라인드 채용 공식 가이드라인에 따라 자기소개서에서 불적격 처리 사유가 되는 표현을 찾아내세요.
원문을 수정하거나 치환하지 말고, 위험한 표현을 그대로 추출하여 목록으로 반환하세요.

{_MUST_DETECT}

{_DIRECT_CATEGORIES}

{_SCORE_GUIDE}

{_VERIFY_STEP}

각 탐지 항목: text(원문 표현 그대로), type(카테고리명), reason(왜 불적격인지 한 줄)으로 기록하세요.
일반적인 표현은 제외하고, 가이드라인에 명시된 불적격 사유에 해당하는 표현만 추출하세요.""",

    "high": f"""당신은 블라인드 채용 전문가입니다. 아래 한국 블라인드 채용 공식 가이드라인에 따라 자기소개서에서 불적격 처리 사유가 되는 표현을 찾아내세요. 직접 언급뿐 아니라 간접적으로 유추 가능한 표현까지 모두 탐지하세요.
원문을 수정하거나 치환하지 말고, 위험한 표현을 그대로 추출하여 목록으로 반환하세요.

{_MUST_DETECT}

{_DIRECT_CATEGORIES}

{_HIGH_CONTEXTUAL}

{_SCORE_GUIDE}

{_VERIFY_STEP}

각 탐지 항목: text(원문 표현 그대로), type(카테고리명), reason(왜 불적격인지 한 줄)으로 기록하세요.
일반적인 표현은 제외하고, 가이드라인 기준에서 불적격 사유에 해당하거나 신원을 유추할 수 있는 표현만 추출하세요.""",
}

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "detection_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "risky_entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "type": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["text", "type", "reason"],
                        "additionalProperties": False,
                    },
                },
                "risk_score": {"type": "integer"},
            },
            "required": ["risky_entities", "risk_score"],
            "additionalProperties": False,
        },
    },
}


def detect(text: str, sensitivity: str = "high") -> dict:
    """텍스트에서 신원 식별 가능한 표현을 탐지하여 반환합니다."""
    if sensitivity not in ("low", "high"):
        raise ValueError(f"sensitivity는 'low' 또는 'high'여야 합니다: {sensitivity!r}")

    try:
        response = client.chat.completions.create(
            model="solar-pro3",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS[sensitivity]},
                {
                    "role": "user",
                    "content": (
                        "다음 자기소개서에서 블라인드 채용 기준에 위배되는 "
                        "신원 식별 가능한 표현을 모두 찾아 반환하세요.\n\n"
                        f"[원문]\n{text}"
                    ),
                },
            ],
            response_format=_RESPONSE_FORMAT,
            max_tokens=2048,
            temperature=0.1,
            timeout=30,
        )
    except Exception as exc:
        raise RuntimeError(f"Upstage API 호출 실패: {exc}") from exc

    return json.loads(response.choices[0].message.content)


def _load_payload(args: argparse.Namespace) -> dict:
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return json.load(f)
    if args.text:
        return {"text": args.text, "sensitivity": args.sensitivity}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw, "sensitivity": args.sensitivity}


def main():
    parser = argparse.ArgumentParser(description="블라인드 채용 자기소개서 위험 표현 탐지")
    parser.add_argument("--text", help="분석할 텍스트 (직접 입력)")
    parser.add_argument("--file", help='JSON 입력 파일 경로 ({"text":…,"sensitivity":…})')
    parser.add_argument("--sensitivity", choices=["low", "high"], default="high",
                        help="탐지 민감도: low=직접 개인정보만, high=문맥적 정보 포함 (기본값: high)")
    args = parser.parse_args()

    payload = _load_payload(args)
    text = payload.get("text", "")
    sensitivity = payload.get("sensitivity", args.sensitivity)

    if not text:
        print(json.dumps({"error": "분석할 텍스트가 없습니다. --text, --file, 또는 stdin으로 입력하세요."}, ensure_ascii=False))
        sys.exit(1)

    try:
        result = detect(text, sensitivity)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
