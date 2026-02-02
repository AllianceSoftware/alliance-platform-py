import importlib
import inspect
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

from multiproject.utils import get_project
from sphinx import addnodes
from sphinx.domains.std import Cmdoption

current_dir = Path(__file__).parent
sys.path.append(str(current_dir / "_doc_utils"))

from ap_doc_utils import generate_sidebar  # noqa

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Alliance Platform"
copyright = "2024, Alliance Software"
author = "Alliance Software"


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.intersphinx",
    "multiproject",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_rtd_theme",
    "sphinx.ext.linkcode",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = []

autodoc_typehints = "description"

# -- Options for Multiproject extension --------------------------------------
multiproject_projects = {
    "core": {
        "name": "Core",
        "path": "../packages/ap-core/docs",
    },
    "frontend": {
        "name": "Frontend",
        "path": "../packages/ap-frontend/docs",
    },
    "codegen": {
        "name": "Codegen",
        "path": "../packages/ap-codegen/docs",
    },
    "storage": {
        "name": "Storage",
        "path": "../packages/ap-storage/docs",
    },
    "audit": {
        "name": "Audit",
        "path": "../packages/ap-audit/docs",
    },
    "ui": {
        "name": "UI",
        "path": "../packages/ap-ui/docs",
    },
    "pdf": {
        "name": "PDF",
        "path": "../packages/ap-pdf/docs",
    },
    "server-choices": {
        "name": "Server Choices",
        "path": "../packages/ap-server-choices/docs",
    },
    "ordered-model": {
        "name": "Ordered Model",
        "path": "../packages/ap-ordered-model/docs",
    },
}

# -- Options for Intersphinx extension ---------------------------------------

# This is used for linking and such so we link to the thing we're building
is_on_rtd = os.environ.get("READTHEDOCS", None) == "True"
rtd_version = os.environ.get("READTHEDOCS_VERSION", "latest")
rtd_url = os.environ.get(
    "READTHEDOCS_CANONICAL_URL", f"https://alliance-platform.readthedocs.io/en/{rtd_version}/"
)
parts = urlparse(rtd_url)
base_url = f"{parts.scheme}://{parts.hostname}"

dev_port_map = {
    "core": 56675,
    "frontend": 56676,
    "codegen": 56677,
    "storage": 56678,
    "audit": 56679,
    "ui": 56680,
    "pdf": 56681,
    "server-choices": 56682,
    "ordered-model": 56683,
}


def get_project_mapping(project_name: str):
    if is_on_rtd:
        if project_name == "core":
            return (f"{base_url}/en/{rtd_version}/", None)
        return (f"{base_url}/projects/{project_name}/{rtd_version}/", None)
    port = dev_port_map[project_name]
    # In dev load from the local dev server started by build-docs-watch. Load the objects.inv from the filesystem;
    # this only works after the first build. We can't load from the dev server because it's not running yet (sphinx
    # reads it immediately on startup)
    return (f"http://127.0.0.1:{port}/", str(current_dir / f"../_docs-build/{project_name}/objects.inv"))


intersphinx_mapping = {
    "alliance-platform-core": get_project_mapping("core"),
    "alliance-platform-frontend": get_project_mapping("frontend"),
    "alliance-platform-codegen": get_project_mapping("codegen"),
    "alliance-platform-storage": get_project_mapping("storage"),
    "alliance-platform-audit": get_project_mapping("audit"),
    "alliance-platform-ui": get_project_mapping("ui"),
    "alliance-platform-pdf": get_project_mapping("pdf"),
    "alliance-platform-server-choices": get_project_mapping("server-choices"),
    "alliance-platform-ordered-model": get_project_mapping("ordered-model"),
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        ("https://docs.djangoproject.com/en/stable/_objects/"),
    ),
    "python": ("https://docs.python.org/3", None),
}

# Sphinx defaults to automatically resolve *unresolved* labels using all your Intersphinx mappings.
# This behavior has unintended side-effects, namely that documentations local references can
# suddenly resolve to an external location.
# See also:
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#confval-intersphinx_disabled_reftypes
intersphinx_disabled_reftypes = ["*"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

docset = get_project(multiproject_projects)
docset_path = (current_dir / multiproject_projects[docset]["path"]).relative_to(current_dir.parent)

html_theme = "sphinx_rtd_theme"

html_context = {
    "display_github": True,
    "github_user": "AllianceSoftware",
    "github_repo": "alliance-platform-py",
    "github_version": "main",
    # Path in the checkout to the docs root, handle multiple-project setup
    "conf_py_path": f"/{docset_path}/",
}


def parse_management_command(env, sig, signode):
    command = sig.split(" ")[0]
    env.ref_context["std:program"] = command
    title = "./manage.py %s" % sig
    signode += addnodes.desc_name(title, title)
    return command


def setup(app):
    # Allows using `:ttag:` and `:tfilter:` roles in the documentation to link to template tags and filters.
    app.add_crossref_type(
        directivename="templatetag",
        rolename="ttag",
        indextemplate="pair: %s; template tag",
    )
    app.add_crossref_type(
        directivename="templatefilter",
        rolename="tfilter",
        indextemplate="pair: %s; template filter",
    )
    # Allows usage of setting role, e.g. :setting:`FORM_RENDERER <django:FORM_RENDERER>`
    app.add_crossref_type(
        directivename="setting",
        rolename="setting",
        indextemplate="pair: %s; setting",
    )
    app.add_object_type(
        directivename="django-manage",
        rolename="djmanage",
        indextemplate="pair: %s; django-manage command",
        parse_node=parse_management_command,
    )
    app.add_directive("django-manage-option", Cmdoption)


generate_sidebar(current_dir, globals())

git_identifier = os.environ.get("READTHEDOCS_GIT_IDENTIFIER", "main")


def linkcode_resolve(domain, info):
    """Handle resolving URL for the linkcode extension.

    See https://www.sphinx-doc.org/en/master/usage/extensions/linkcode.html#confval-linkcode_resolve
    """
    if domain != "py":
        return None
    if not info["module"]:
        return None
    filename = info["module"].replace(".", "/")
    try:
        # e.g. alliance_platform/frontend/whatever
        # project will be 'frontend'
        package, project, _ = filename.rsplit("/", 2)
    except ValueError:
        return None
    if package != "alliance_platform":
        return None
    obj_name, *parts = info["fullname"].split(".")
    obj = getattr(importlib.import_module(info["module"]), obj_name)
    try:
        if parts:
            try:
                _, linenum = inspect.getsourcelines(getattr(obj, parts[0]))
            except (TypeError, AttributeError):
                # This will happen when getattr above returns a variable instead of method
                _, linenum = inspect.getsourcelines(obj)
        else:
            _, linenum = inspect.getsourcelines(obj)
    except TypeError:
        # May fail still, e.g. for types
        linenum = 0
    return f"https://github.com/AllianceSoftware/alliance-platform-py/blob/{git_identifier}/packages/ap-{project}/{filename}.py#L{linenum}"
