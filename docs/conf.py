from pathlib import Path

from multiproject.utils import get_project

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
]

templates_path = ["_templates"]
exclude_patterns: list[str] = []

autodoc_typehints = "description"

# -- Options for Multiproject extension --------------------------------------
multiproject_projects = {
    "core": {
        "path": "../packages/ap-core/docs",
    },
    "frontend": {
        "path": "../packages/ap-frontend/docs",
    },
    "codegen": {
        "path": "../packages/ap-codegen/docs",
    },
}

# -- Options for Intersphinx extension ---------------------------------------
intersphinx_mapping = {
    "alliance-platform-frontend": (
        "https://alliance-platform.readthedocs.io/projects/frontend/latest/",
        None,
    ),
    "alliance-platform-codegen": ("https://alliance-platform.readthedocs.io/projects/codegen/latest/", None),
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        ("https://docs.djangoproject.com/en/stable/_objects/"),
    ),
    "python": ("https://docs.python.org/3", "https://docs.python.org/3/objects.inv"),
}
# Sphinx defaults to automatically resolve *unresolved* labels using all your Intersphinx mappings.
# This behavior has unintended side-effects, namely that documentations local references can
# suddenly resolve to an external location.
# See also:
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#confval-intersphinx_disabled_reftypes
intersphinx_disabled_reftypes = ["*"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

current_dir = Path(__file__).parent
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
