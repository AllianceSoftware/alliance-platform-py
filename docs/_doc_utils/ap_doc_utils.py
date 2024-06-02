from pathlib import Path
from textwrap import dedent
from textwrap import indent


def generate_sidebar(doc_dir: Path, conf):
    """Generates the sidebar for the documentation that includes links to each subproject."""
    target = doc_dir / "../packages/ap-core/docs/_sidebar.rst.inc"
    links = []
    for name, proj_conf in conf["multiproject_projects"].items():
        url = conf["intersphinx_mapping"][f"alliance-platform-{name}"][0]
        links.append(f"{proj_conf['name']} <{url}>")
    contents = dedent("""
    .. toctree::
        :caption: Package Docs
        :maxdepth: 2
        
    """)
    contents += indent("\n".join(links), "    ")

    if not target.exists() or target.read_text() != contents:
        target.write_text(contents)
