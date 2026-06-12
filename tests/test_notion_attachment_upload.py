import base64
import unittest

from app.attachments.models import InputAttachment
from app.attachments.notion_upload import NotionAttachmentUploader, NotionAttachmentUploadError


class FakeNotionClient:
    def __init__(self):
        self.descriptors = []
        self.enqueued = []
        self.signed_requests = []

    def request_upload_descriptor(self, name, content_type, size, thread_id, create_thread):
        desc = {
            "upload_url": f"https://upload.test/{name}",
            "fields": {"k": "v"},
            "file_id": f"file-{name}",
            "attachment_url": f"attachment:file-{name}:block",
            "chat_id": "thread-from-descriptor",
            "metadata": {"name": name},
        }
        self.descriptors.append((name, content_type, size, thread_id, create_thread))
        return desc

    def perform_multipart_upload(self, descriptor, name, data, content_type):
        # record that upload was called; in real code this would POST to descriptor['upload_url']
        self.last_upload = {"descriptor": descriptor, "name": name, "size": len(data), "content_type": content_type}

    def enqueue_attachment_processing(self, attachment_url, thread_id):
        self.enqueued.append((attachment_url, thread_id))
        return f"task-{attachment_url.split(':')[1]}"

    def get_task_status(self, task_id):
        # immediate success for tests
        return {"status": "completed", "success": True}

    def get_signed_read_url(self, attachment_url, thread_id="", download_name=""):
        self.signed_requests.append((attachment_url, thread_id, download_name))
        return f"https://signed.test/{attachment_url.split(':')[1]}"


class NotionAttachmentUploadTests(unittest.TestCase):
    def test_upload_attachments_success(self):
        client = FakeNotionClient()
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001)

        # inline base64 attachment (use allowed MIME type: text/csv)
        data_b64 = base64.b64encode(b"hello,world\n").decode()
        att = InputAttachment(name="greet.csv", content_type="text/csv", source="inline_data", data=data_b64)

        uploaded, thread = uploader.upload_attachments(thread_id="thread-1", attachments=[att], create_thread=False)

        self.assertEqual(thread, "thread-from-descriptor")
        self.assertEqual(len(uploaded), 1)
        u = uploaded[0]
        self.assertTrue(u.file_id.startswith("file-"))
        self.assertTrue(u.signed_get_url.startswith("https://signed.test/"))
        # descriptor was requested with expected params
        self.assertEqual(client.descriptors[0][0], "greet.csv")
        self.assertEqual(client.last_upload["size"], len(b"hello,world\n"))
        self.assertEqual(client.enqueued[0], ("attachment:file-greet.csv:block", "thread-from-descriptor"))
        self.assertEqual(client.signed_requests[0], ("attachment:file-greet.csv:block", "thread-from-descriptor", "greet.csv"))

    def test_task_failure_raises(self):
        client = FakeNotionClient()
        # override get_task_status to fail
        def failing_status(task_id):
            return {"status": "failed", "success": False}

        client.get_task_status = failing_status
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001)

        data_b64 = base64.b64encode(b"%PDF-1.4\n%fakepdf\n").decode()
        att = InputAttachment(name="bad.pdf", content_type="application/pdf", source="inline_data", data=data_b64)

        with self.assertRaises(NotionAttachmentUploadError):
            uploader.upload_attachments(thread_id="t", attachments=[att], create_thread=False)

    def test_missing_client_method_fails(self):
        # client missing required methods should fail closed
        class IncompleteClient:
            pass

        client = IncompleteClient()
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001)
        data_b64 = base64.b64encode(b"hello,world\n").decode()
        att = InputAttachment(name="greet.csv", content_type="text/csv", source="inline_data", data=data_b64)

        with self.assertRaises(NotionAttachmentUploadError):
            uploader.upload_attachments(thread_id="t", attachments=[att], create_thread=False)

    def test_incomplete_descriptor_fails(self):
        # descriptor missing upload_url and file_id should be rejected
        class BadDescriptorClient(FakeNotionClient):
            def request_upload_descriptor(self, name, content_type, size, thread_id, create_thread):
                return {"fields": {}}  # incomplete

        client = BadDescriptorClient()
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001)
        data_b64 = base64.b64encode(b"hello,world\n").decode()
        att = InputAttachment(name="greet.csv", content_type="text/csv", source="inline_data", data=data_b64)

        with self.assertRaises(NotionAttachmentUploadError):
            uploader.upload_attachments(thread_id="t", attachments=[att], create_thread=False)

    def test_multipart_upload_failure_propagates(self):
        class FailUploadClient(FakeNotionClient):
            def perform_multipart_upload(self, descriptor, name, data, content_type):
                raise RuntimeError("upload failed")

        client = FailUploadClient()
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001)
        data_b64 = base64.b64encode(b"hello,world\n").decode()
        att = InputAttachment(name="greet.csv", content_type="text/csv", source="inline_data", data=data_b64)

        with self.assertRaises(NotionAttachmentUploadError):
            uploader.upload_attachments(thread_id="t", attachments=[att], create_thread=False)

    def test_task_timeout_fails(self):
        class SlowTaskClient(FakeNotionClient):
            def get_task_status(self, task_id):
                return {"status": "pending"}

        client = SlowTaskClient()
        uploader = NotionAttachmentUploader(notion_client=client, poll_interval=0.001, poll_timeout=0.01)
        data_b64 = base64.b64encode(b"hello,world\n").decode()
        att = InputAttachment(name="greet.csv", content_type="text/csv", source="inline_data", data=data_b64)

        with self.assertRaises(NotionAttachmentUploadError):
            uploader.upload_attachments(thread_id="t", attachments=[att], create_thread=False)

    def test_build_metadata_excludes_sensitive(self):
        client = FakeNotionClient()
        uploader = NotionAttachmentUploader(notion_client=client)
        sample = {"fileSizeBytes": 123, "contentType": "text/csv", "source": "inline_data", "taskId": "task-1", "fileId": "file-1", "signedUrl": "https://x", "raw": b"bytes"}
        meta = uploader.build_attachment_step_metadata(sample)
        self.assertIn("fileSizeBytes", meta)
        self.assertIn("contentType", meta)
        self.assertNotIn("signedUrl", meta)
        self.assertNotIn("raw", meta)


if __name__ == "__main__":
    unittest.main()
