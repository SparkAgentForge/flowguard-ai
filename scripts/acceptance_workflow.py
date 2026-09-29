"""Exercise the HTTP workflow on an explicitly isolated acceptance instance.

Uses only the Python standard library. Real mode never changes providers or
invents a PASS. Mock mode uses a clearly named two-step fixture to cover every
state branch. Keep the JSONL record until the owning test resources are cleaned.
"""

import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.base = args.base_url.rstrip("/")
        self.actor = f"test-{args.run_id}"[:100]
        self.records = []
        self.ids = {"work_orders": [], "documents": [], "versions": []}

    def record(self, item):
        item["time"] = time.time()
        self.records.append(item)
        with open(self.args.output, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def call(self, method, path, payload=None, file=None, expected=(200,), binary=False):
        headers = {}
        body = None
        if file:
            filename, content, media_type = file
            boundary = uuid.uuid4().hex
            body = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\nContent-Type: {media_type}\r\n\r\n'
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        started = time.monotonic()
        try:
            response = urllib.request.urlopen(request, timeout=2400)
        except urllib.error.HTTPError as error:
            response = error
        status = response.status
        content = response.read()
        response.close()
        parsed = content if binary else (json.loads(content) if content else None)
        record = {"method": method, "path": path, "http": status,
                  "seconds": round(time.monotonic() - started, 2)}
        if isinstance(parsed, dict):
            record["result"] = {key: parsed[key] for key in
                                ("id", "status", "decision", "provider", "modelName", "detail")
                                if key in parsed}
        elif binary:
            record["bytes"] = len(content)
        self.record(record)
        assert status in expected, f"{method} {path}: {status}, {record.get('result')}"
        return parsed

    def api(self, method, path, **kwargs):
        return self.call(method, "/api/v1" + path, **kwargs)

    def prepare_sop(self):
        if self.args.version_id:
            version = self.api("GET", f"/sop-versions/{self.args.version_id}")
        else:
            if self.args.mode == "mock":
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    archive.writestr("word/document.xml", (
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        '<w:body><w:p><w:r><w:t>（1）安装第一个风扇。</w:t></w:r></w:p>'
                        '<w:p><w:r><w:t>（2）安装第二个风扇。</w:t></w:r></w:p>'
                        '</w:body></w:document>'
                    ))
                filename, content = f"{self.args.run_id}-mock-fixture.docx", output.getvalue()
            else:
                filename, content = self.args.manual.name, self.args.manual.read_bytes()
            document = self.api("POST", "/documents", expected=(201,), file=(
                filename, content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            self.ids["documents"].append(document["id"])
            duplicate = self.api("POST", "/documents", expected=(201,), file=(filename, content, "application/octet-stream"))
            assert duplicate["id"] == document["id"]
            version = self.api("POST", f"/documents/{document['id']}/extract", payload={"actorId": self.actor})
        self.ids["versions"].append(version["id"])
        self.record({"stage": "sop", "version_id": version["id"], "steps": version["steps"]})
        if version["status"] == "AI_EXTRACTED":
            version = self.api("PUT", f"/sop-versions/{version['id']}", payload={
                "actorId": self.actor, "name": version["name"],
                "productCode": version["productCode"], "steps": version["steps"]})
            self.api("POST", f"/sop-versions/{version['id']}/publish", payload={"actorId": self.actor}, expected=(409,))
            for action, status in (("submit-review", "IN_REVIEW"), ("approve", "APPROVED"), ("publish", "PUBLISHED")):
                version = self.api("POST", f"/sop-versions/{version['id']}/{action}", payload={"actorId": self.actor})
                assert version["status"] == status
        assert version["status"] == "PUBLISHED"
        assert any(item["id"] == version["id"] for item in self.api("GET", "/sop-versions"))
        return version

    def order(self, version, label):
        order = self.api("POST", "/work-orders", expected=(201,), payload={
            "code": f"{self.args.run_id}-{label}", "productCode": version["productCode"],
            "sopVersionId": version["id"]})
        self.ids["work_orders"].append(order)
        self.api("GET", f"/work-orders/{order['id']}")
        return order

    def inspect(self, order, filename, content, decision=None):
        video = self.api("POST", f"/work-orders/{order['id']}/videos", expected=(201,), file=(filename, content, "video/mp4"))
        assert any(item["id"] == video["id"] for item in self.api("GET", f"/work-orders/{order['id']}/videos"))
        audit = self.api("POST", f"/work-orders/{order['id']}/inspect", expected=(201,), payload={"videoId": video["id"], "actorId": self.actor})
        assert audit["status"] == "COMPLETED", audit
        if decision:
            assert audit["decision"] == decision, audit["decision"]
        detail = self.api("GET", f"/work-orders/{order['id']}/audits/{audit['id']}")
        assert detail["videoId"] == video["id"] and detail["workOrderId"] == order["id"]
        audits = self.api("GET", f"/work-orders/{order['id']}/audits")
        assert any(item["id"] == audit["id"] for item in audits)
        repeated = self.api("POST", f"/work-orders/{order['id']}/inspect", expected=(201,), payload={"videoId": video["id"], "actorId": self.actor})
        assert repeated["id"] == audit["id"]
        self.record({"stage": "audit_evidence", "work_order_id": order["id"], "audit": detail})
        return audit, video

    def exception(self, order):
        cases = self.api("GET", "/exceptions")
        case = next(item for item in cases if item["workOrderId"] == order["id"])
        return self.api("GET", f"/exceptions/{case['id']}")

    def report(self, order):
        report = self.api("GET", f"/reports/{order['id']}")
        pdf = self.api("GET", f"/reports/{order['id']}/pdf", binary=True)
        assert pdf.startswith(b"%PDF")
        assert hashlib.sha256(pdf).hexdigest() == report["pdfSha256"]
        assert self.api("GET", f"/reports/{order['id']}")["id"] == report["id"]
        self.record({"stage": "report", "work_order_id": order["id"], "id": report["id"], "pdf_sha256": report["pdfSha256"], "outcome": report["content"]["outcome"]})

    def run(self):
        health = self.api("GET", "/health")
        assert health["inference_provider"] == ("mock" if self.args.mode == "mock" else "stepfun")
        spec = self.call("GET", "/api/openapi.json")
        self.record({"stage": "openapi", "paths": len(spec["paths"]), "operations": sum(len([m for m in methods if m in {"get", "post", "put", "delete", "patch"}]) for methods in spec["paths"].values())})
        self.api("POST", "/documents", file=("bad.txt", b"invalid", "text/plain"), expected=(415,))
        self.api("POST", "/documents", file=("empty.pdf", b"", "application/pdf"), expected=(400,))
        self.api("GET", "/work-orders/not-a-real-id", expected=(404,))
        self.api("POST", "/work-orders", payload={}, expected=(422,))
        version = self.prepare_sop()
        if self.args.mode == "real":
            order = self.order(version, self.args.video.stem)
            audit, video = self.inspect(order, self.args.video.name, self.args.video.read_bytes())
            self.api("GET", f"/work-orders/{order['id']}/videos/{video['id']}/content", binary=True)
            for finding in audit["findings"]:
                for kind, flag in (("confirmed", "hasConfirmedClip"), ("candidate", "hasCandidateClip")):
                    if finding[flag]:
                        self.api("GET", f"/work-orders/{order['id']}/audits/{audit['id']}/findings/{finding['sopStepId']}/clip?kind={kind}", binary=True)
            if audit["decision"] == "PASS":
                self.report(order)
            else:
                self.exception(order)
                self.api("GET", f"/reports/{order['id']}", expected=(409,))
        else:
            normal = self.order(version, "normal")
            self.inspect(normal, "normal.mp4", b"mock video fixture", "PASS")
            self.report(normal)
            self.api("POST", f"/work-orders/{normal['id']}/transitions", payload={"targetStatus": "ARCHIVED", "actorId": self.actor, "reason": "test archive"})
            self.api("DELETE", f"/work-orders/{normal['id']}", payload={"actorId": self.actor, "confirmation": normal["code"]}, expected=(409,))
            missing = self.order(version, "missing")
            self.inspect(missing, "missing-step.mp4", b"mock missing", "VIOLATION")
            case = self.exception(missing)
            self.api("POST", f"/exceptions/{case['id']}/confirm", payload={"actorId": self.actor, "reason": "Isolated mock fixture: confirm missing step"})
            assigned = self.api("POST", f"/exceptions/{case['id']}/rework-task", expected=(201,), payload={"actorId": self.actor, "assigneeId": self.actor, "instructions": "Isolated acceptance: resubmit full operation"})
            task = assigned["reworkTask"]["id"]
            assert any(item["reworkTaskId"] == task for item in self.api("GET", f"/notifications?recipient_id={self.actor}"))
            video = self.api("POST", f"/rework-tasks/{task}/videos", expected=(201,), file=("rework-normal.mp4", b"mock rework", "video/mp4"))
            assert any(item["id"] == video["id"] for item in self.api("GET", f"/work-orders/{missing['id']}/videos"))
            assert self.api("GET", f"/exceptions/{case['id']}")["status"] == "REWORK_SUBMITTED"
            review = self.api("POST", f"/rework-tasks/{task}/review", payload={"actorId": self.actor, "videoId": video["id"], "notes": "Isolated acceptance review"})
            assert review["audit"]["decision"] == "PASS"
            assert review["workOrder"]["status"] == "RELEASED"
            self.api("GET", f"/work-orders/{missing['id']}/audits/{review['audit']['id']}")
            self.report(missing)
            occluded = self.order(version, "occluded")
            audit, _ = self.inspect(occluded, "occluded.mp4", b"mock occluded", "INSUFFICIENT_EVIDENCE")
            requests = self.api("GET", f"/work-orders/{occluded['id']}/audits/{audit['id']}/review-requests")
            assert requests
            self.api("POST", f"/work-orders/{occluded['id']}/audits/{audit['id']}/review-requests/{requests[0]['id']}/resolve", payload={"actorId": self.actor, "decision": "CONFIRMED", "note": "Mock evidence review"})
            case = self.exception(occluded)
            self.api("POST", f"/exceptions/{case['id']}/reject", payload={"actorId": self.actor, "reason": "Mock false-positive rejection branch"})
            self.api("DELETE", f"/work-orders/{occluded['id']}", payload={"actorId": self.actor, "confirmation": occluded["code"]}, expected=(204,))
            self.api("GET", f"/work-orders/{occluded['id']}", expected=(404,))
        self.api("GET", "/work-orders")
        self.api("GET", "/reports")
        self.record({"stage": "complete", "result": "PASS", "resources": self.ids})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--mode", choices=("mock", "real"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manual", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--version-id")
    parser.add_argument("--output", required=True)
    parser.add_argument("--isolated-test-instance", action="store_true", required=True)
    args = parser.parse_args()
    if args.mode == "real" and (not args.manual or not args.video):
        parser.error("Real mode requires --manual and --video")
    runner = Acceptance(args)
    try:
        runner.run()
    except Exception as error:
        runner.record({"stage": "failed", "error": str(error), "resources": runner.ids})
        raise


if __name__ == "__main__":
    main()
