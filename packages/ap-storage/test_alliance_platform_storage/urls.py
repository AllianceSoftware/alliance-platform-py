from alliance_platform.storage.async_uploads.registry import default_async_field_registry

app_name = "test_alliance_platform_storage"


urlpatterns = [*default_async_field_registry.get_url_patterns()]
