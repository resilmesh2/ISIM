from pathlib import Path

import streamlit.components.v1 as components

_RELEASE = True

if not _RELEASE:
    _component_func = components.declare_component(
        # We give the component a simple, descriptive name ("my_component"
        # does not fit this bill, so please choose something better for your
        # own component :)
        "monaco_react",
        # Pass `url` here to tell Streamlit that the component will be served
        # by the local dev server that you run via `npm run start`.
        # (This is useful while your component is in development.)
        url="http://localhost:3000",
    )
else:
    # When we're distributing a production version of the component, we'll
    # replace the `url` param with `path`, and point it to the component's
    # build directory:
    parent_dir = Path(__file__).parent
    build_dir = parent_dir / "frontend/build"
    _component_func = components.declare_component("monaco_react", path=build_dir)


def monaco_prql_react(name: str, key: str | None = None) -> str:
    return _component_func(name=name, key=key)
