from markdown_toc import generate_toc


def test_nested_toc():
    md = "# Title\n\n## Install\n\n## Usage\n\n### Advanced Usage\n"
    toc = generate_toc(md)
    assert "- [Title](#title)" in toc
    assert "  - [Install](#install)" in toc
    assert "    - [Advanced Usage](#advanced-usage)" in toc


def test_headings_in_code_fences_are_ignored():
    md = "# Real\n\n```\n# Not A Heading\n```\n"
    toc = generate_toc(md)
    assert "Not A Heading" not in toc
    assert "- [Real](#real)" in toc


def test_slug_punctuation():
    md = "## What's New: v2.0!\n"
    assert "(#whats-new-v20)" in generate_toc(md)
