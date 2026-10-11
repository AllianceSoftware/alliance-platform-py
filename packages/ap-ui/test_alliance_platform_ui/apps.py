from django.apps import AppConfig


class UITestProjectConfig(AppConfig):
    name = "test_alliance_platform_ui"

    def ready(self):
        # Import renderers here rather than at module level: apps.py is imported while Django is
        # still loading apps.
        from alliance_platform.ui.html_components import register_component

        from .static_components import StatRenderer
        from .static_components import StatValueRenderer

        register_component("stat", StatRenderer)
        register_component("stat_value", StatValueRenderer)
