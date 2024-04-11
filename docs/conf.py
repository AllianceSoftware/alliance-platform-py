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
    "alliance-platform-frontend": ("https://alliance-platform.readthedocs.io/projects/frontend/", None),
    "alliance-platform-codegen": ("https://alliance-platform.readthedocs.io/projects/codegen/", None),
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

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
