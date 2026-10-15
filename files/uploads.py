"""Upload handler that enforces the per-file size limit while the file arrives.

A form can check `item.size` only after Django has written the whole upload to
a temporary file, so one oversized request could fill the server disk before
any check ran. This handler sits first in FILE_UPLOAD_HANDLERS and counts the
bytes of every file as they stream in. Once a file passes
FILE_MANAGER["MAX_FILE_SIZE"], the rest of it is skipped (read from the
network and dropped, never written), and its name is recorded on the request
so that the upload form can tell the user why the file is missing.
"""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, SkipFile

#: Request attribute with the names of the files that were too large.
OVERSIZED_ATTR = "oversized_uploads"


class SizeLimitUploadHandler(FileUploadHandler):
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > settings.FILE_MANAGER["MAX_FILE_SIZE"]:
            oversized_uploads(self.request).append(self.file_name or "")
            raise SkipFile
        return raw_data

    def file_complete(self, file_size):
        # The next handlers build the file object.
        return None


def oversized_uploads(request) -> list[str]:
    """Names of the files dropped from this request for being too large."""
    if not hasattr(request, OVERSIZED_ATTR):
        setattr(request, OVERSIZED_ATTR, [])
    return getattr(request, OVERSIZED_ATTR)
