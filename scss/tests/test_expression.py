# -*- coding: utf-8 -*-
"""Tests for expressions -- both their evaluation and their general
parsability.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from scss.calculator import Calculator
from scss.errors import SassEvaluationError
from scss.errors import SassSyntaxError
from scss.extension.core import CoreExtension
from scss.types import Color, List, Null, Number, String
from scss.types import Function

import pytest


@pytest.fixture
def calc():
    return Calculator().evaluate_expression


def assert_strict_string_eq(expected, actual):
    assert expected.value == actual.value
    assert expected.quotes == actual.quotes


def test_reference_operations():
    """Test the example expressions in the reference document:

    http://sass-lang.com/docs/yardoc/file.SASS_REFERENCE.html#operations
    """
    # TODO: break this into its own file and add the entire reference guide

    # Need to build the calculator manually to get at its namespace, and need
    # to use calculate() instead of evaluate_expression() so interpolation
    # works
    ns = CoreExtension.namespace.derive()
    calc = Calculator(ns).calculate

    # Simple example
    assert calc('1in + 8pt') == Number(1.1111111111111112, "in")

    # Division
    ns.set_variable('$width', Number(1000, "px"))
    ns.set_variable('$font-size', Number(12, "px"))
    ns.set_variable('$line-height', Number(30, "px"))
    assert calc('10px/8px') == String('10px / 8px')   # plain CSS; no division
    assert calc('$width/2') == Number(500, "px")      # uses a variable; does division
    assert calc('(500px/2)') == Number(250, "px")     # uses parens; does division
    assert calc('5px + 8px/2px') == Number(9, "px")   # uses +; does division
    # TODO, again: Ruby Sass correctly renders this without spaces
    assert calc('#{$font-size}/#{$line-height}') == String('12px / 30px')
                                            # uses #{}; does no division

    # Modulo
    assert calc('29 % 12') == Number(5)
    assert calc('29px % 12') == Number(5, 'px')
    assert calc('29px % 12px') == Number(5, 'px')

    # Color operations
    ns.set_variable('$translucent-red', Color.from_rgb(1, 0, 0, 0.5))
    ns.set_variable('$green', Color.from_name('lime'))
    assert calc('#010203 + #040506') == Color.from_hex('#050709')
    assert calc('#010203 * 2') == Color.from_hex('#020406')
    assert calc('rgba(255, 0, 0, 0.75) + rgba(0, 255, 0, 0.75)') == Color.from_rgb(1, 1, 0, 0.75)
    assert calc('opacify($translucent-red, 0.3)') == Color.from_rgb(1, 0, 0, 0.8)
    assert calc('transparentize($translucent-red, 0.25)') == Color.from_rgb(1, 0, 0, 0.25)
    assert calc("progid:DXImageTransform.Microsoft.gradient(enabled='false', startColorstr='#{ie-hex-str($green)}', endColorstr='#{ie-hex-str($translucent-red)}')"
                ).render() == "progid:DXImageTransform.Microsoft.gradient(enabled='false', startColorstr='#FF00FF00', endColorstr='#80FF0000')"

    # String operations
    ns.set_variable('$value', Null())
    assert_strict_string_eq(calc('e + -resize'), String('e-resize', quotes=None))
    assert_strict_string_eq(calc('"Foo " + Bar'), String('Foo Bar', quotes='"'))
    assert_strict_string_eq(calc('sans- + "serif"'), String('sans-serif', quotes=None))
    assert calc('3px + 4px auto') == List([Number(7, "px"), String('auto', quotes=None)])
    assert_strict_string_eq(calc('"I ate #{5 + 10} pies!"'), String('I ate 15 pies!', quotes='"'))
    assert_strict_string_eq(calc('"I ate #{$value} pies!"'), String('I ate  pies!', quotes='"'))


def test_functions(calc):
    calc = Calculator(CoreExtension.namespace).calculate

    assert calc('grayscale(red)') == Color.from_rgb(0.5, 0.5, 0.5)
    assert calc('grayscale(1)') == String('grayscale(1)', quotes=None)  # Misusing css built-in functions (with scss counterpart)
    assert calc('skew(1)') == String('skew(1)', quotes=None)  # Missing css-only built-in functions
    with pytest.raises(SassEvaluationError):
        calc('unitless("X")')  # Misusing non-css built-in scss funtions


def test_parse_strings(calc):
    # Escapes in barewords are preserved.
    assert calc('auto\\9') == String.unquoted('auto\\9')

    # Escapes in quoted strings are expanded.
    assert calc('"\\2022"') == String("•", quotes='"')
    assert calc('"\\2022"').render() == '"•"'


def test_parse_bang_important(calc):
    # The !important flag is treated as part of a spaced list.
    assert calc('40px !important') == List([
        Number(40, 'px'), String.unquoted('!important'),
    ], use_comma=False)

    # And is allowed anywhere in the string.
    assert calc('foo !important bar') == List([
        String('foo'), String('!important'), String('bar'),
    ], use_comma=False)

    # And may have space before the !.
    assert calc('40px ! important') == List([
        Number(40, 'px'), String.unquoted('!important'),
    ], use_comma=False)


def test_parse_special_functions():
    ns = CoreExtension.namespace.derive()
    calc = Calculator(ns).calculate

    # expression() allows absolutely any old garbage inside
    # TODO we can't deal with an unmatched { due to the block locator, but ruby
    # can
    for gnarly_expression in (
            "not ~* remotely *~ valid {syntax}",
            "expression( ( -0 - floater.offsetHeight + ( document"
            ".documentElement.clientHeight ? document.documentElement"
            ".clientHeight : document.body.clientHeight ) + ( ignoreMe"
            " = document.documentElement.scrollTop ? document"
            ".documentElement.scrollTop : document.body.scrollTop ) ) +"
            " 'px' )"):
        expr = 'expression(' + gnarly_expression + ')'
        assert calc(expr).render() == expr

    # alpha() doubles as a special function if it contains opacity=n, the IE
    # filter syntax
    assert calc('alpha(black)') == Number(1)
    assert calc('alpha(opacity = 5)') == Function('opacity=5', 'alpha')
    assert calc('alpha(opacity = 5)').render() == 'alpha(opacity=5)'

    # url() allows both an opaque URL and a Sass expression, based on some
    # heuristics
    ns.set_variable('$foo', String.unquoted('foo'))
    assert calc('url($foo)').render() == "url(foo)"
    assert calc('url(#{$foo}foo)').render() == "url(foofoo)"
    assert calc('url($foo + $foo)').render() == "url(foofoo)"
    # TODO this one doesn't work if $foo has quotes; Url.render() tries to
    # escape them.  which i'm not sure is wrong, but we're getting into
    # territory where it's obvious bad output...
    assert calc('url($foo + #{$foo})').render() == "url(foo + foo)"
    assert calc('url(foo #{$foo} foo)').render() == "url(foo foo foo)"
    with pytest.raises(SassSyntaxError):
        # Starting with #{} means it's a url, which can't contain spaces
        calc('url(#{$foo} foo)')
    with pytest.raises(SassSyntaxError):
        # Or variables
        calc('url(#{$foo}$foo)')
    with pytest.raises(SassSyntaxError):
        # This looks like a URL too
        calc('url(foo#{$foo} foo)')


# TODO write more!  i'm lazy.
# TODO assert things about particular kinds of parse /errors/, too
# TODO errors really need to be more understandable  :(  i think this requires
# some additions to yapps
