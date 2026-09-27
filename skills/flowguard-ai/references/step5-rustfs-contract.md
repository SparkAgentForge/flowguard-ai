# Step 5 and RustFS visual contract

Step 5 must receive images it can actually fetch. RustFS is the durable
intermediate evidence store; it is not optional when using the Step 5 provider.

## Manual pages

For PDF manuals:

```text
PDF -> render each page to PNG -> put page image in RustFS
    -> create a time-limited presigned URL -> send image_url to Step 5
    -> validate the structured candidate SOP and its page/source reference
```

The PDF path is image-based. Do not silently switch to text-layer extraction
when the configured Step 5 extractor fails. DOCX may use the repository's
deterministic extractor according to the configured provider.

## Video frames

The Step 5 video adapter follows:

```text
video bytes -> FFmpeg/ffprobe -> JPEG frames
            -> RustFS object keys: step5-frames/<run>/frame-<seconds>.jpg
            -> presigned image URLs
            -> Step 5 /chat/completions
            -> structured findings
```

The request must carry real timestamps and the SOP step payload. The model is
instructed to select only evidence frames it actually sees; the service derives
the start/end range from selected timestamps. Object keys, sampled timestamps,
model responses, and retry information remain in the audit raw response.

## Endpoint separation

- `FLOWGUARD_OBJECT_STORAGE_ENDPOINT` is the API container's internal RustFS
  endpoint used for writes.
- `FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT` is the URL that Step 5 can fetch.

Reject localhost, loopback, private, or link-local presigned URLs when Step 5
is remote. A URL that is valid inside Docker but unreachable by Step 5 is a
configuration failure, not a model failure.

## Evidence rules

- Never inline frame bytes as base64 in the Step 5 request.
- Never treat a high model confidence as proof when no valid frame timestamp or
  evidence exists.
- Keep the frame object key after its presigned URL expires.
- Clean up only frame objects created by the current test run.
- Do not log API keys or complete signed URLs.

