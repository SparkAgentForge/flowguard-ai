# Step 5 and RustFS visual contract

Step 5 receives inline image data in the API request. RustFS is the durable
intermediate evidence store; it is not optional when using the Step 5 provider.

## Manual pages

For PDF manuals:

```text
PDF -> render each page to PNG -> put page image in RustFS
    -> encode PNG as a base64 data URL -> send image_url to Step 5
    -> validate the structured candidate SOP and its page/source reference
```

The PDF path is image-based. Do not silently switch to text-layer extraction
when the configured Step 5 extractor fails. DOCX may use the repository's
deterministic extractor according to the configured provider.

## Video frames

The Step 5 video adapter follows:

```text
video bytes -> FFmpeg/ffprobe -> JPEG frames
            -> RustFS object keys: step5-frames/<work-order-id>/<run>/frame-<seconds>.jpg
            -> base64 JPEG data URLs
            -> Step 5 /chat/completions
            -> structured findings
```

The request must carry real timestamps and the SOP step payload. The model is
instructed to select only evidence frames it actually sees; the service derives
the start/end range from selected timestamps. Object keys, sampled timestamps,
model responses, and retry information remain in the audit raw response.
The work-order prefix lets deletion find frames even when inference fails
before an audit record is committed; legacy frame keys remain discoverable
through recorded audit metadata.

## Endpoint separation

- `FLOWGUARD_OBJECT_STORAGE_ENDPOINT` is the API container's internal RustFS
  endpoint used for writes.
- `FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT` is used for browser-facing
  presigned previews, not Step 5 analysis.

Step 5 needs no route back to RustFS. A private RustFS endpoint is sufficient
when the API can write objects there. Avoid logging request bodies because
they contain complete image data.
The [official Step 5 vision guide](https://platform.stepfun.com/docs/zh/guides/developer/image-chat)
supports Base64 data URLs for `step-5-preview` and limits each request to 60
images. It recommends URLs for performance, but inline data avoids requiring
public RustFS access. The current frame and page caps are below that count;
request-body size can still be limiting.

## Evidence rules

- Send PNG and JPEG as `data:image/png;base64,...` and
  `data:image/jpeg;base64,...` inside `image_url.url`.
- Never treat a high model confidence as proof when no valid frame timestamp or
  evidence exists.
- Keep the frame object key for durable evidence; do not persist data URLs in
  audit records.
- Clean up only frame objects created by the current test run.
- Do not log API keys or inline images. Limit image count/size to stay within
  the Step 5 request limit; report upstream size errors clearly.
