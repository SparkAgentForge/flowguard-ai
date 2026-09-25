from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def put(self, key: str, content: bytes) -> None:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def get_url(self, key: str, expires_seconds: int = 900) -> str:
        raise RuntimeError("本地文件存储没有可供 Step 5 访问的 HTTP URL")

    def _resolve(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("非法存储路径")
        return target


class S3FileStorage:
    """S3-compatible storage for RustFS and local development."""

    def __init__(
        self,
        endpoint: str,
        public_endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        if not access_key or not secret_key:
            raise ValueError("RustFS 存储已启用，但未配置 access key 或 secret key")
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
        except ImportError as error:
            raise RuntimeError("RustFS 存储需要安装 boto3 依赖") from error
        self.bucket = bucket
        self._endpoint = endpoint.rstrip("/")
        self._public_endpoint = (public_endpoint or endpoint).rstrip("/")
        self._client_kwargs = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
            "endpoint_url": self._endpoint,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client = boto3.client("s3", **self._client_kwargs)
        self._public_client = boto3.client(
            "s3", **{**self._client_kwargs, "endpoint_url": self._public_endpoint}
        )
        self._client_error = ClientError
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except self._client_error:
            self._client.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

    def put(self, key: str, content: bytes) -> None:
        self._ensure_bucket()
        self._client.put_object(Bucket=self.bucket, Key=key, Body=content)

    def get(self, key: str) -> bytes:
        self._ensure_bucket()
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def get_url(self, key: str, expires_seconds: int = 900) -> str:
        self._ensure_bucket()
        return self._public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
