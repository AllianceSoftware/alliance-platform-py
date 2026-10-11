"""System check support for the frontend build."""

#: Tag for system checks that verify what a frontend build depends on, such as the npm packages
#: installed in ``node_modules``. A check registered with it runs with the other system checks and
#: also inside :djmanage:`extract_frontend_resources`, before any template is read: an error it
#: reports that is not silenced in ``SILENCED_SYSTEM_CHECKS`` fails the command, and so the build
#: that runs it, even with ``--skip-checks``. Register a check with the tag as with any other::
#:
#:     from django.core import checks
#:
#:     from alliance_platform.frontend.checks import FRONTEND_BUILD_CHECK_TAG
#:
#:     checks.register(check_my_package, FRONTEND_BUILD_CHECK_TAG)
FRONTEND_BUILD_CHECK_TAG = "alliance_platform_frontend_build"
