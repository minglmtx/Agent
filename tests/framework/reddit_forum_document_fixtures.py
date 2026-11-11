"""Minimal original template structure; no Postmill, credentials or writable state."""


def document(case: str) -> str:
    if case not in (
        "normal",
        "empty",
        "missing-tab",
        "duplicate-tab",
        "missing-list",
        "wrong-form",
        "hidden-tab",
    ):
        raise ValueError("Unknown explicit forum document fixture")
    tab = (
        '<ul class="unlistify flex"><li><a class="tab tab--active" href="/forums/all"'
        + (' style="display:none"' if case == "hidden-tab" else "")
        + ">Alphabetical</a></li></ul>"
    )
    links = (
        ""
        if case == "empty"
        else '<div class="text-flow"><h2>E</h2><ul class="unlistify"><li><a href="/f/EarthPorn">EarthPorn</a></li></ul></div>'
    )
    return (
        "<html><body>"
        + ("" if case == "missing-tab" else tab * (2 if case == "duplicate-tab" else 1))
        + '<h1 class="page-heading">All forums</h1>'
        + (
            ""
            if case == "missing-list"
            else '<div class="columns flow">' + links + "</div>"
        )
        + (
            '<input name="submission[image]" type="file">'
            if case == "wrong-form"
            else ""
        )
        + "</body></html>"
    )
