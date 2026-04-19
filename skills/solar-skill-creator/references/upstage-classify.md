# Upstage Document Classification

Verified on: 2026-04-19

## What it does
Buckets any document into one of a caller-defined set of category labels and returns the winning label plus a confidence score. Use this to route mixed-format document streams (invoices, contracts, receipts, CVs, etc.) to the right downstream pipeline without writing any classification logic yourself — no templates and no retraining required.

## When to choose this over related capabilities
Use Document Classification when you receive documents of unknown or mixed types and need to know _what_ the document is before acting on it. The other five capabilities serve different shapes of work:

- **Chat (Solar LLM)** — text generation and conversation; you would have to write classification prompts and parse free-form output yourself, with no built-in confidence scores.
- **Document Parse** — returns the full document body with layout structure (headings, tables, paragraphs) as HTML/Markdown; it does not classify the document type.
- **Document OCR** — returns raw text plus word-level bounding boxes; does not classify.
- **Information Extract (Universal)** — pulls specific named fields (e.g., `invoice_total`, `contract_date`) from a document; assumes you already know the document type. The canonical pipeline is: **Classification → if invoice, run Information Extract with invoice schema; if contract, run contract schema**.
- **Embeddings** — vectorizes text for semantic search and similarity; can support retrieval-based classification but requires you to maintain a labeled embedding corpus.

Concrete pattern: receive a batch of incoming files → Classify each → branch on the returned category → pass to the correct downstream extractor or handler.

## Constraints checklist
- Max file size: 50 MB
- Max pages (sync): 100 pages per document
- Max resolution: 200,000,000 pixels per page
- Min category count: 1 class required
- Max category count: 1,000 document classes per request
- Duplicate class handling: classes with duplicate `const` names are silently ignored
- Language / locale support: Not specified in docs — verify against current Upstage docs before use
- Async variant: Sync only (confirmed in docs)
- Custom vs prebuilt: Categories are fully caller-defined; the raw API accepts any label set you define

## Supported formats
- Input: JPEG, PNG, BMP, PDF, TIFF, HEIC, DOCX, PPTX, XLSX, HWP, HWPX — submitted as a base64 data URL inside a Chat Completions `image_url` content part; plus a `response_format` JSON Schema body defining the category list
- Output: The winning category label delivered as a string in `choices[0].message.content`; confidence score (nested under `document_type`) and per-page split metadata delivered in `choices[0].message.tool_calls[0].function.arguments` as a JSON string (when the API returns it)

## Authentication
Set the environment variable `UPSTAGE_API_KEY` and pass it as a Bearer token:

```
Authorization: Bearer $UPSTAGE_API_KEY
```

When using the OpenAI SDK, supply the key as `api_key` and point `base_url` at the Document Classification endpoint:

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["UPSTAGE_API_KEY"],
    base_url="https://api.upstage.ai/v1/document-classification",
)
```

## API format
**Endpoint**: `POST https://api.upstage.ai/v1/document-classification`

The API follows the OpenAI Chat Completions wire format. The document is attached as a base64 data URL inside the user message's `image_url` content part; the set of valid categories is declared in `response_format` as a `oneOf` enum of `const` values.

**Request**:
```json
{
  "model": "document-classify",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:application/octet-stream;base64,<BASE64_ENCODED_FILE>"
          }
        }
      ]
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "document_type",
      "schema": {
        "type": "string",
        "oneOf": [
          {"const": "invoice",          "description": "A bill issued by a vendor requesting payment for goods or services"},
          {"const": "receipt",          "description": "A proof-of-payment document issued after a transaction is completed"},
          {"const": "contract",         "description": "A legally binding agreement between two or more parties"},
          {"const": "cv",               "description": "A resume or curriculum vitae listing a person's work history and qualifications"},
          {"const": "bank_statement",   "description": "A periodic summary of account transactions issued by a bank"},
          {"const": "others",           "description": "Any document that does not match the above categories"}
        ]
      }
    }
  }
}
```

**Response**:
```json
{
  "id": "clf-AbCdEf1234567890",
  "object": "chat.completion",
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "invoice",
        "tool_calls": [
          {
            "id": "call_additional_values",
            "type": "function",
            "function": {
              "name": "additional_values",
              "arguments": "{\"document_type\":{\"_value\":\"invoice\",\"confidence_score\":0.99},\"pages\":[1],\"split_criteria_info\":null}"
            }
          }
        ]
      }
    }
  ],
  "created": 1745020800,
  "model": "document-classify",
  "usage": {
    "prompt_tokens": 420,
    "completion_tokens": 4,
    "total_tokens": 424
  }
}
```

The winning category is in `choices[0].message.content` as a plain string. The confidence score (0–1) is nested inside `document_type` and the page list is a top-level sibling — parse the JSON string in `choices[0].message.tool_calls[0].function.arguments` and access `args["document_type"]["confidence_score"]` and `args["pages"]`.

**Python example (full runnable)**:
```python
import base64, json, os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["UPSTAGE_API_KEY"],
    base_url="https://api.upstage.ai/v1/document-classification",
)

with open("document.pdf", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = client.chat.completions.create(
    model="document-classify",
    messages=[{
        "role": "user",
        "content": [{
            "type": "image_url",
            "image_url": {"url": f"data:application/octet-stream;base64,{b64}"},
        }],
    }],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "document_type",
            "schema": {
                "type": "string",
                "oneOf": [
                    {"const": "invoice",        "description": "Bill requesting payment for goods or services"},
                    {"const": "receipt",        "description": "Proof-of-payment document after a completed transaction"},
                    {"const": "contract",       "description": "Legally binding agreement between parties"},
                    {"const": "cv",             "description": "Resume or curriculum vitae"},
                    {"const": "bank_statement", "description": "Periodic account transaction summary from a bank"},
                    {"const": "others",         "description": "Any document not matching the above categories"},
                ],
            },
        },
    },
)

category = resp.choices[0].message.content  # e.g. "invoice"

# Confidence score lives in tool_calls additional_values, nested under document_type
tool_calls = resp.choices[0].message.tool_calls
if tool_calls:
    additional = json.loads(tool_calls[0].function.arguments)
    confidence = additional["document_type"]["confidence_score"]  # e.g. 0.99
    pages = additional["pages"]                                   # e.g. [1, 2]
else:
    confidence = None
    pages = None

print(f"Category: {category}, Confidence: {confidence}, Pages: {pages}")

# Route to the right downstream handler
if category == "invoice":
    pass  # run Information Extract with invoice schema
elif category == "contract":
    pass  # run Information Extract with contract schema
```

**Curl example**:
```bash
B64=$(base64 -i document.pdf)

curl -X POST https://api.upstage.ai/v1/document-classification \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "document-classify",
    "messages": [{
      "role": "user",
      "content": [{
        "type": "image_url",
        "image_url": {"url": "data:application/octet-stream;base64,'"$B64"'"}
      }]
    }],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "document_type",
        "schema": {
          "type": "string",
          "oneOf": [
            {"const": "invoice",  "description": "Bill requesting payment for goods or services"},
            {"const": "receipt",  "description": "Proof-of-payment document after a completed transaction"},
            {"const": "contract", "description": "Legally binding agreement between parties"},
            {"const": "others",   "description": "Any document not matching the above categories"}
          ]
        }
      }
    }
  }'
```

## Parameters
| Name | Required | Default | Description |
|---|---|---|---|
| `model` | yes | — | Use `document-classify` (production). `document-classify-nightly` is an experimental alias — not for production use |
| `messages` | yes | — | Array with a single `user` message containing an `image_url` content part whose `url` is a base64 data URL of the document |
| `response_format` | yes | — | Object with `type: "json_schema"` and a `json_schema` object; the `schema` must be `type: "string"` with a `oneOf` array of `{"const": "<label>", "description": "<what this category means>"}` objects |
| `split` | no | `false` | When `true`, the API attempts to detect multiple logical documents within one file and classifies each separately |
| `split_criteria` | no | — | Array of objects providing additional hints for splitting multi-document files; used together with `split: true`. Each object has `criterion` (string) and `description` (string) fields — e.g. `[{"criterion": "card_id", "description": "The id that indicates each unit card."}]` |

## Caveats and gotchas
**Define categories with clear, non-overlapping descriptions.** The model uses the `description` field on each `const` entry to understand what that category means. Vague or overlapping labels reduce accuracy. Prefer `["invoice", "receipt", "purchase_order"]` over `["invoice", "bill", "invoice_or_receipt"]`. Each description should state the distinguishing characteristic of that document type.

**Always include an `"others"` catch-all category.** When documents arrive from an untrusted source, some will not match any of your defined types. Without an `"others"` option the model is forced to pick the nearest category, which can silently misroute documents. Example:
```json
{"const": "others", "description": "Any document that does not match the categories above"}
```

**Too many labels can confuse the model — start with core labels and expand gradually.** The API supports 1–1,000 classes, but classification accuracy degrades as the label space grows and descriptions start to overlap. For larger taxonomies, consider a two-stage approach: coarse classification first (e.g., `financial` / `legal` / `hr`), then fine-grained classification within each bucket.

**Confidence score is not in `message.content` — it is in `tool_calls`.** The returned category string is in `choices[0].message.content`. The confidence score (0.0–1.0) is nested inside the `document_type` object in `choices[0].message.tool_calls[0].function.arguments`: parse that JSON string and access `args["document_type"]["confidence_score"]`. The `pages` list is a top-level sibling of `document_type`, not nested inside it.

**When you have no fixed category list, fall back to Chat.** Document Classification requires a defined label set at call time. If the use-case is open-ended (e.g., "tell me what kind of document this is" without a known taxonomy), use Solar LLM Chat with a structured-output schema instead — Classification will not return meaningful results without concrete `const` values to choose from.

**The base URL for the OpenAI SDK must point to the classification sub-namespace.** Use `base_url="https://api.upstage.ai/v1/document-classification"` when initializing the OpenAI SDK client — not the generic `/v1` root. This mirrors the pattern used by Information Extract (`/v1/information-extraction`).
