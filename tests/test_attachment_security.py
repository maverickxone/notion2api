import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.attachments.errors import AttachmentError
from app.attachments.loader import decode_inline_data, load_attachment_data
from app.attachments.models import InputAttachment
from app.attachments.security import (
    AttachmentPolicy,
    validate_content_type,
    validate_remote_url,
    validate_size,
)


class AttachmentSecurityTests(unittest.TestCase):
    def test_rejects_unsupported_content_type(self) -> None:
        with self.assertRaises(AttachmentError) as ctx:
            validate_content_type("application/x-msdownload", AttachmentPolicy(enabled=True))
        self.assertEqual(ctx.exception.code, "unsupported_attachment_type")

    def test_rejects_oversized_payload(self) -> None:
        with self.assertRaises(AttachmentError) as ctx:
            validate_size(11, AttachmentPolicy(enabled=True, max_attachment_bytes=10))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_blocks_localhost_remote_url(self) -> None:
        with self.assertRaises(AttachmentError) as ctx:
            validate_remote_url("http://localhost/file.pdf", AttachmentPolicy(enabled=True))
        self.assertEqual(ctx.exception.code, "attachment_url_blocked")

    @patch("app.attachments.security.socket.getaddrinfo")
    def test_blocks_private_resolved_address(self, getaddrinfo) -> None:
        getaddrinfo.return_value = [(None, None, None, None, ("192.168.1.50", 0))]
        with self.assertRaises(AttachmentError) as ctx:
            validate_remote_url("https://example.test/file.pdf", AttachmentPolicy(enabled=True))
        self.assertEqual(ctx.exception.code, "attachment_url_blocked")

    @patch("app.attachments.security.socket.getaddrinfo")
    def test_allows_public_resolved_address(self, getaddrinfo) -> None:
        getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        self.assertEqual(
            validate_remote_url("https://example.com/file.pdf", AttachmentPolicy(enabled=True)),
            "https://example.com/file.pdf",
        )

    def test_decode_data_url(self) -> None:
        payload = base64.b64encode(b"hello").decode("ascii")
        data, content_type = decode_inline_data(f"data:text/csv;base64,{payload}")
        self.assertEqual(data, b"hello")
        self.assertEqual(content_type, "text/csv")

    def test_load_inline_attachment(self) -> None:
        payload = base64.b64encode(b"a,b\n1,2\n").decode("ascii")
        loaded = load_attachment_data(
            InputAttachment(
                name="records.csv",
                content_type="text/csv",
                source="inline_data",
                data=payload,
            ),
            AttachmentPolicy(enabled=True),
        )

        self.assertEqual(loaded.name, "records.csv")
        self.assertEqual(loaded.content_type, "text/csv")
        self.assertEqual(loaded.data, b"a,b\n1,2\n")

    def test_local_path_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.pdf"
            path.write_bytes(b"%PDF")
            with self.assertRaises(AttachmentError) as ctx:
                load_attachment_data(
                    InputAttachment(
                        name="file.pdf",
                        content_type="application/pdf",
                        source="local_path",
                        path=str(path),
                    ),
                    AttachmentPolicy(enabled=True, allow_local_paths=False),
                )
            self.assertEqual(ctx.exception.code, "local_attachment_paths_disabled")


if __name__ == "__main__":
    unittest.main()
