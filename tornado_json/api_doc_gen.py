import logging
import json
import inspect

import tornado.web
from jsonschema import validate, ValidationError
try:
    from itertools import imap as map
except ImportError:
    pass

from tornado_json.utils import is_method
from tornado_json.constants import HTTP_METHODS
from tornado_json.requesthandlers import APIHandler


def _validate_example(rh, method, example_type):
    """Validates example against schema

    :returns: Formatted example if example exists and validates, otherwise None
    :raises ValidationError: If example does not validate against the schema
    """
    example = getattr(method, example_type + "_example")
    schema = getattr(method, example_type + "_schema")

    if example is None:
        return None

    try:
        validate(example, schema)
    except ValidationError as e:
        raise ValidationError(
            "{}_example for {}.{} could not be validated.\n{}".format(
                example_type, rh.__name__, method.__name__, str(e)
            )
        )

    return json.dumps(example, indent=4)


def _get_rh_methods(rh):
    """Yield all HTTP methods in ``rh`` that are decorated
    with schema.validate"""
    for k, v in vars(rh).items():
        if all([
            k in HTTP_METHODS,
            is_method(v),
            hasattr(v, "input_schema")
        ]):
            yield (k, v)


def _get_tuple_from_route(route):
    """Return (pattern, handler_class) tuple from ``route``

    :type route: tuple|tornado.web.URLSpec
    :rtype: tuple
    :raises TypeError: If ``route`` is not a tuple or URLSpec
    """
    if isinstance(route, tuple):
        assert len(route) >= 2
        pattern, handler_class = route[:2]
    elif isinstance(route, tornado.web.URLSpec):
        pattern, handler_class = route.regex.pattern, route.handler_class
    else:
        raise TypeError("Unknown route type '{}'"
                        .format(type(route).__name__))
    return pattern, handler_class


def _write_docs_to_file(documentation):
    # Documentation is written to the root folder
    with open("API_Documentation.md", "w+") as f:
        f.write(
            "**This documentation is automatically generated.**\n\n" +
            "**Output schemas only represent `data` and not the full output; "
            "see output examples and the JSend specification.**\n" +
            "\n<br>\n<br>\n".join(documentation)
        )


def _escape_markdown_literals(string):
    """Escape any markdown literals in ``string`` by prepending with \\

    :type string: str
    :rtype: str
    """
    literals = list("\\`*_{}[]()<>#+-.!:|")
    escape = lambda c: '\\' + c if c in literals else c
    return "".join(map(escape, string))


def cleandoc(doc):
    """Remove uniform indents from ``doc`` lines that are not empty

    :returns: Cleaned ``doc``
    """
    indent_length = lambda s: len(s) - len(s.lstrip(" "))
    not_empty = lambda s: s != ""

    lines = doc.split("\n")
    indent = min(map(indent_length, filter(not_empty, lines)))

    return "\n".join(s[indent:] for s in lines)


def add_indent(string, indent):
    """Add indent of ``indent`` spaces to ``string.split("\n")[1:]``

    Useful for formatting in strings to already indented blocks
    """
    lines = string.split("\n")
    first, lines = lines[0], lines[1:]
    lines = ["{indent}{s}".format(indent=" "*indent, s=s)
         for s in lines]
    lines = [first] + lines
    return "\n".join(lines)


def _get_example_doc(rh, method, type):
    assert type in ("input", "output")

    example = _validate_example(rh, method, type)
    if not example:
        return ""
    res = """
    **{type} Example**
    ```json
    {example}
    ```
    """.format(
        type=type.capitalize(),
        example=add_indent(example, 4)
    )
    return cleandoc(res)


def _get_input_example(rh, method):
    return _get_example_doc(rh, method, "input")


def _get_output_example(rh, method):
    return _get_example_doc(rh, method, "output")


def _get_schema_doc(schema, type):
    res = """
    **{type} Schema**
    ```json
    {schema}
    ```
    """.format(
        schema=add_indent(json.dumps(schema, indent=4), 4),
        type=type.capitalize()
    )
    return cleandoc(res)


def _get_input_schema_doc(method):
    return _get_schema_doc(method.input_schema, "input")


def _get_output_schema_doc(method):
    return _get_schema_doc(method.output_schema, "output")


def _get_notes(method):
    res = """
    **Notes**

    {}
    """.format(
        add_indent(inspect.getdoc(method), 4)
    )
    return cleandoc(res)


def _get_method_doc(rh, method_name, method):
    res = """## {method_name}

    {input_schema}
    {input_example}
    {output_schema}
    {output_example}
    {notes}
    """.format(
        method_name=method_name.upper(),
        input_schema=_get_input_schema_doc(method),
        output_schema=_get_output_schema_doc(method),
        notes=_get_notes(method),
        input_example=_get_input_example(rh, method),
        output_example=_get_output_example(rh, method),
    )
    return cleandoc("\n".join([l.rstrip() for l in res.splitlines()]))


def _get_rh_doc(rh):
    res = "\n\n".join([_get_method_doc(rh, method_name, method)
                       for method_name, method in _get_rh_methods(rh)])
    return res


def _get_route_doc(url, rh):
    # TODO: Content-type is hard-coded but ideally should be retrieved;
    #  the hard part is, we don't know what it is without initializing
    #  an instance, so just leave as-is for now

    # BEGIN ROUTE_DOC #
    route_doc = """
# {0}

    Content-Type: application/json

{1}
""".format(
        _escape_markdown_literals(url),
        _get_rh_doc(rh)
    )
    # END ROUTE_DOC #
    return route_doc


def api_doc_gen(routes):
    """
    Generates GitHub Markdown formatted API documentation using
    provided schemas in RequestHandler methods and their docstrings.

    :type  routes: [(url, RequestHandler), ...]
    :param routes: List of routes (this is ideally all possible routes of the
        app)
    """
    routes = map(_get_tuple_from_route, routes)

    documentation = []
    for url, rh in sorted(routes, key=lambda a: a[0]):
        if issubclass(rh, APIHandler):
            documentation.append(_get_route_doc(url, rh))

    _write_docs_to_file(documentation)
