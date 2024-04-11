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

extensions = ["multiproject", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx_rtd_theme"]

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

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
