import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_dsm_help_is_generated_from_documentation_core_during_ui_build():
    makefile = (ROOT / "ui" / "Makefile").read_text(encoding="utf-8")
    renderer = ROOT / "tools" / "docs" / "render_dsm_help.py"

    assert renderer.is_file()
    assert "DSM_HELP_RENDERER=../tools/docs/render_dsm_help.py" in makefile
    assert "all: dsm-help" in makefile
    assert "install: dsm-help" in makefile
    assert "python3 $(DSM_HELP_RENDERER)" in makefile
    assert "cp -a help $(INSTALLDIR)" in makefile
    assert "install -m 644 helptoc.conf $(INSTALLDIR)/helptoc.conf" in makefile


def test_dsm_help_renderer_uses_dsm_74_file_station_shell_and_locale_mapping():
    renderer = (ROOT / "tools" / "docs" / "render_dsm_help.py").read_text(encoding="utf-8")

    assert 'LOCALES = {"de": "ger", "en": "enu"}' in renderer
    assert 'DEFAULT_TOC_PATH = REPO_ROOT / "ui" / "helptoc.conf"' in renderer
    assert 'read_info_value(info_path, "dsmappname")' in renderer
    assert 'HELPTOC_TITLE = "helptoc:imgdata"' in renderer
    assert '../../../../help/help.css' in renderer
    assert '../../../../help/scrollbar/flexcroll.css' in renderer
    assert '../../../../help/scrollbar/flexcroll.js' in renderer
    assert '../../../../help/scrollbar/initFlexcroll.js' in renderer
    assert 'index_page and level == 2' in renderer
    assert 'level = 4' in renderer


def test_dsm_help_index_remains_documentation_core_source_of_truth():
    german = (ROOT / "docs" / "core" / "de" / "index.md").read_text(encoding="utf-8")
    english = (ROOT / "docs" / "core" / "en" / "index.md").read_text(encoding="utf-8")

    assert "id: index" in german
    assert "id: index" in english
    assert "# ImgData" in german
    assert "# ImgData" in english
    assert "## Status" in german
    assert "## Status" in english
    assert "[[doc:" not in german
    assert "[[doc:" not in english


def test_dsm_help_toc_registers_existing_localized_pages():
    toc = json.loads((ROOT / "ui" / "helptoc.conf").read_text(encoding="utf-8"))
    info = (ROOT / "INFO.sh").read_text(encoding="utf-8")

    assert 'dsmappname="SYNO.SDS.App.AV_ImgData.Instance"' in info
    assert toc == {
        "app": "SYNO.SDS.App.AV_ImgData.Instance",
        "title": "helptoc:imgdata",
        "content": "index.html",
        "helpset": "help",
        "stringset": "texts",
        "toc": [
            {
                "title": "nav:status",
                "content": "status.html",
            }
        ],
    }

    for language in ("ger", "enu"):
        assert (ROOT / "ui" / "help" / language / "index.html").is_file()
        assert (ROOT / "ui" / "help" / language / "status.html").is_file()
        strings = (ROOT / "ui" / "texts" / language / "strings").read_text(encoding="utf-8")
        assert "[helptoc]" in strings
        assert 'imgdata="ImgData"' in strings
        assert "[nav]" in strings
        assert 'status="Status"' in strings
