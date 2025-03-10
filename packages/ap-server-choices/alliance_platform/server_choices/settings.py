from typing import TYPE_CHECKING
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase

if TYPE_CHECKING:
    pass


class AlliancePlatformServerChoicesSettingsType(TypedDict, total=False):
    """Settings for the Server Choices package of the Alliance Platform
    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:
    .. code-block:: python
        ALLIANCE_PLATFORM = {
            "SERVER_CHOICES": {
                # settings go here
            }
        }
    """

    #: The default paginator to use when returning choice results. Supports the API of DRF paginators.
    #: Defaults to :class:`~alliance_platform.server_choices.pagination.SimplePaginator`
    DEFAULT_PAGINATION_CLASS: int | None
    #: The page size to use for the default pagination handler. Note that if using a DRF paginator,
    #: it will use the internal DRF settings for page size instead.
    PAGE_SIZE: int | None


class AlliancePlatformServerChoicesSettings(AlliancePlatformSettingsBase):
    #: The default paginator to use when returning choice results. Supports the API of DRF paginators.
    #: Defaults to :class:`~alliance_platform.server_choices.pagination.SimplePaginator`
    DEFAULT_PAGINATION_CLASS: str | None
    #: The page size to use for the default pagination handler. Note that if using a DRF paginator,
    #: it will use the internal DRF settings for page size instead.
    PAGE_SIZE: int


DEFAULTS = {
    "DEFAULT_PAGINATION_CLASS": "alliance_platform.server_choices.pagination.SimplePaginator",
    "PAGE_SIZE": 20,
}

ap_server_choices_settings = AlliancePlatformServerChoicesSettings(
    "SERVER_CHOICES",
    import_strings=["DEFAULT_PAGINATION_CLASS"],
    defaults=DEFAULTS,
)
