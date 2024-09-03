from alliance_platform.storage.base import AsyncUploadStorage
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DummyStorage(AsyncUploadStorage, Storage):
    def generate_upload_url(self, name, **kwargs):
        return f"http://signme.com/{name}"

    def generate_download_url(self, key, **kwargs):
        return f"http://downloadme.com/{key}"

    def move_file(self, from_key, to_key):
        pass

    def exists(self, name):
        return False

    def _open(self, name, mode):
        raise NotImplementedError()
