---
name: blind-hiring-anonymizer
description: >
  블라인드 채용 자기소개서 위험 표현 탐지 스킬. 이름·전화번호 같은 직접 개인정보를 넘어 "○○대 대동제", "○○타워 근무", "강남구 거주" 처럼 문맥상 신원을 드러내는 정황 표현까지 찾아내어 원문 표현·유형·위험 이유를 목록으로 반환합니다. 사용자가 아래 중 하나라도 언급하면 반드시 이 스킬을 활성화하세요:
  자기소개서 검토 / 블라인드 채용 확인 / 개인정보 탐지 / cover letter check / 신원 노출 여부 확인 / 자소서에서 위험한 부분 찾아줘 / 문맥적 개인정보 탐지. 사용자가 글을 붙여넣으면 즉시 분석을 시작하세요.
---

# 블라인드 채용 위험 표현 탐지 (Blind Hiring Detector)

자기소개서에서 블라인드 채용 기준에 위배되는 표현을 **탐지하여 목록으로 반환**합니다.  
원문을 수정·치환하지 않고, 위험한 표현과 그 이유만 짚어줍니다.

## 스킬 구조

```
skills/blind-hiring-anonymizer/
├── SKILL.md
├── scripts/
│   ├── anonymize.py        ← 실행 진입점 + 핵심 로직
│   └── requirements.txt
└── assets/
    ├── .env.example        ← API 키 템플릿
    └── .env                ← 실제 API 키 (git 커밋 금지)
```

## 처음 설정

### 1단계 — 의존성 설치

```bash
pip install -r skills/blind-hiring-anonymizer/scripts/requirements.txt
```

### 2단계 — Upstage API 키 설정

1. [console.upstage.ai](https://console.upstage.ai) 에서 API 키 발급
2. 추천 코드 `UPWAVE-KOH` 입력 → $70 크레딧 즉시 적립
3. `.env` 파일 생성:

```bash
cp skills/blind-hiring-anonymizer/assets/.env.example skills/blind-hiring-anonymizer/assets/.env
```

`.env`를 열어 `your-upstage-api-key-here` 자리에 실제 키를 입력합니다.

---

## 사용자가 텍스트를 붙여넣었을 때 처리 절차

사용자가 자기소개서 텍스트를 제공하면 아래 절차를 따르세요.

### 1. 입력 파일 작성

Write 툴로 `skills/blind-hiring-anonymizer/assets/input.json`에 저장합니다:

```json
{
  "text": "<사용자가 붙여넣은 텍스트>",
  "sensitivity": "high"
}
```

`sensitivity`는 사용자가 명시하지 않으면 `"high"`를 기본값으로 사용합니다.

### 2. 스크립트 실행

```bash
python skills/blind-hiring-anonymizer/scripts/anonymize.py --file skills/blind-hiring-anonymizer/assets/input.json
```

### 3. 결과 해석 및 보고

출력 JSON을 파싱하여 다음 형식으로 사용자에게 보고합니다:

**보고 템플릿:**
```
## 블라인드 채용 점검 결과

**위험도 점수: {risk_score}/100** — {위험 수준 설명}

### 위험 표현 ({risky_entities 수}건)
| 원문 표현 | 유형 | 위험 이유 |
|-----------|------|-----------|
| … | … | … |
```

위험 수준 설명 기준:
- 0–20: 낮음 (식별 위험 거의 없음)
- 21–50: 보통 (일부 정보 노출)
- 51–80: 높음 (여러 식별 단서 존재)
- 81–100: 매우 높음 (즉시 수정 필요)

---

## 입출력 형식

### Input

```json
{
  "text": "string — 분석할 자기소개서 원문",
  "sensitivity": "low | high"
}
```

| sensitivity | 탐지 범위 |
|-------------|-----------|
| `low` | 직접 개인정보만 (이름, 연락처, 학교명, 주소, 가족정보 등) |
| `high` | 직접 개인정보 + 문맥적 식별 정보 (행사명, 지역명, 건물명, 조직명 등) |

### Output

```json
{
  "risky_entities": [
    {
      "text": "원문에서 발견된 표현 그대로",
      "type": "유형 (예: 교육기관, 근무지, 지역)",
      "reason": "왜 블라인드 채용 기준에 위배되는지 한 줄 설명"
    }
  ],
  "risk_score": 0
}
```

`risk_score`는 0–100 정수. 탐지된 항목의 수와 심각도를 기반으로 Solar LLM이 산출합니다.  
원문은 수정하지 않습니다 — 어떤 표현이 왜 위험한지만 반환합니다.

---

## 직접 실행 예시

```bash
# stdin으로 JSON 입력
echo '{"text":"저는 한국대학교 컴퓨터공학과 출신으로 강남구에 거주하고 있습니다.","sensitivity":"high"}' \
  | python skills/blind-hiring-anonymizer/scripts/anonymize.py

# --text 플래그
python skills/blind-hiring-anonymizer/scripts/anonymize.py \
  --text "저는 한국대학교 출신입니다." \
  --sensitivity low

# --file 플래그 (Claude Code에서 권장)
python skills/blind-hiring-anonymizer/scripts/anonymize.py \
  --file skills/blind-hiring-anonymizer/assets/input.json
```

## 출력 예시

입력:
```
저는 연세대학교 경영학과 3학년으로, 강남구 소재 OO타워에서 6개월간 인턴십을 수행했습니다.
010-1234-5678로 연락 주시면 감사하겠습니다.
```

출력 (`sensitivity: high`):
```json
{
  "risky_entities": [
    {"text": "연세대학교", "type": "교육기관", "reason": "특정 대학교명으로 출신 학교 특정 가능"},
    {"text": "강남구", "type": "지역", "reason": "시·군·구 수준의 거주 지역으로 신원 범위 특정 가능"},
    {"text": "OO타워", "type": "근무지", "reason": "특정 건물명으로 근무처 식별 가능"},
    {"text": "010-1234-5678", "type": "연락처", "reason": "직접 개인 연락처"}
  ],
  "risk_score": 63
}
```

## 주의사항

- `assets/.env`는 절대 git에 커밋하지 마세요.
- `assets/input.json`도 민감 데이터를 담으므로 커밋하지 마세요.
- `sensitivity: "high"`가 기본값입니다. 보수적으로 걸러야 할 때 사용하세요.
- Solar LLM이 문맥을 이해하므로 같은 단어라도 맥락에 따라 탐지 여부가 달라질 수 있습니다.
